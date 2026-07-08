"""
Migration Runner - Executes migrations in order

Tracks applied migrations and handles dependencies.
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import importlib.util

from .migration import Migration

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Manages database migrations

    Features:
    - Version tracking via schema_migrations table
    - Dependency resolution
    - Dry-run mode
    - Rollback support
    - Auto-discovery of migration files
    """

    def __init__(
        self,
        repository: 'TimescaleDBRepository',
        migrations_path: Optional[str] = None
    ):
        """
        Initialize migration runner

        Args:
            repository: TimescaleDB repository instance
            migrations_path: Path to migrations directory
        """
        self.repo = repository
        self.migrations_path = migrations_path or Path(__file__).parent
        self._migrations: Dict[str, Migration] = {}
        self._load_migrations()

    def _load_migrations(self) -> None:
        """
        Discover and load migration classes

        Looks for files matching migration_*.py in the migrations directory.
        """
        migrations_dir = Path(self.migrations_path)
        if not migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {migrations_dir}")
            return

        for migration_file in migrations_dir.glob("migration_*.py"):
            # Skip __init__ and base migration
            if migration_file.name.startswith("__") or migration_file.name == "migration.py":
                continue

            try:
                # Import the module
                module_name = f"libs.db_repo.migrations.{migration_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, migration_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find Migration classes
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type) and
                        issubclass(attr, Migration) and
                        attr != Migration and
                        hasattr(attr, 'version')
                    ):
                        migration_instance = attr(pool=self.repo.pool)
                        self._migrations[migration_instance.version] = migration_instance
                        logger.debug(f"Loaded migration: {migration_instance.name}")

            except Exception as e:
                logger.error(f"Failed to load migration {migration_file}: {e}")

        # Sort by version
        self._migrations = dict(sorted(self._migrations.items()))

    async def ensure_schema_table(self) -> None:
        """
        Create schema_migrations table if it doesn't exist

        This table tracks which migrations have been applied.
        """
        async with self.repo.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(20) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    applied_at TIMESTAMPTZ NOT NULL,
                    execution_time_ms INTEGER,
                    checksum VARCHAR(64)
                );
            """)
            logger.debug("Schema migrations table ensured")

    async def get_applied_migrations(self) -> Dict[str, Any]:
        """
        Get list of applied migrations from database

        Returns:
            Dict mapping version to migration metadata
        """
        await self.ensure_schema_table()

        async with self.repo.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT version, name, description, applied_at, execution_time_ms
                FROM schema_migrations
                ORDER BY applied_at ASC
            """)

        return {row['version']: dict(row) for row in rows}

    async def get_pending_migrations(self) -> List[Migration]:
        """
        Get migrations that haven't been applied yet

        Returns:
            List of pending migrations in dependency order
        """
        applied = await self.get_applied_migrations()
        pending = []

        for version, migration in self._migrations.items():
            if version not in applied:
                # Check dependencies
                deps_satisfied = all(dep in applied for dep in migration.depends_on)
                if deps_satisfied:
                    pending.append(migration)
                else:
                    logger.warning(
                        f"Migration {migration.name} has unmet dependencies: {migration.depends_on}"
                    )

        return pending

    async def migrate(
        self,
        target_version: Optional[str] = None,
        dry_run: bool = False,
        steps: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Run pending migrations

        Args:
            target_version: Stop at this version (None = all pending)
            dry_run: Show what would be done without executing
            steps: Number of migrations to run (0 = all pending)

        Returns:
            List of migration results
        """
        logger.info("Starting migration process")
        if dry_run:
            logger.warning("DRY RUN MODE - No changes will be applied")

        pending = await self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return []

        # Filter by target version
        if target_version:
            pending = [m for m in pending if m.version <= target_version]

        # Limit by steps
        if steps > 0:
            pending = pending[:steps]

        results = []

        for migration in pending:
            result = await self._apply_migration(migration, dry_run)
            results.append(result)

            if not result.get('success', False):
                logger.error(f"Migration {migration.name} failed, stopping")
                break

        logger.info(f"Migration complete: {len([r for r in results if r['success']])} applied")
        return results

    async def _apply_migration(
        self,
        migration: Migration,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Apply a single migration

        Args:
            migration: Migration to apply
            dry_run: Skip actual execution

        Returns:
            Result dict with success status
        """
        logger.info(f"Applying migration: {migration.name}")

        start_time = datetime.now()
        result = {
            'version': migration.version,
            'name': migration.name,
            'description': migration.description,
            'success': False,
            'error': None,
            'execution_time_ms': None
        }

        try:
            # Validate migration prerequisites
            if not dry_run:
                is_valid = await migration.validate()
                if not is_valid:
                    raise ValueError("Migration validation failed")

            # Apply migration
            if not dry_run:
                await migration.up()

            # Record migration
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            if not dry_run:
                await self._record_migration(migration, execution_time)

            result['success'] = True
            result['execution_time_ms'] = execution_time
            migration.log("Applied successfully")

        except Exception as e:
            result['error'] = str(e)
            migration.log(f"Failed: {e}", "error")
            logger.error(f"Migration {migration.name} failed: {e}")

        return result

    async def _record_migration(
        self,
        migration: Migration,
        execution_time_ms: int
    ) -> None:
        """
        Record applied migration in schema_migrations table

        Args:
            migration: Applied migration
            execution_time_ms: Execution time in milliseconds
        """
        async with self.repo.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO schema_migrations (version, name, description, applied_at, execution_time_ms)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (version) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    applied_at = EXCLUDED.applied_at,
                    execution_time_ms = EXCLUDED.execution_time_ms
            """,
                migration.version,
                migration.name,
                migration.description,
                datetime.now(),
                execution_time_ms
            )

    async def rollback(
        self,
        target_version: Optional[str] = None,
        steps: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Rollback migrations

        Args:
            target_version: Rollback to this version
            steps: Number of migrations to rollback (default: 1)

        Returns:
            List of rollback results
        """
        logger.warning("Starting rollback")
        applied = await self.get_applied_migrations()

        # Get versions to rollback
        versions = list(applied.keys())

        if target_version:
            if target_version not in versions:
                raise ValueError(f"Version {target_version} not found in applied migrations")
            idx = versions.index(target_version)
            versions = versions[idx + 1:]  # Rollback everything after target
        else:
            versions = versions[-steps:] if steps > 0 else []

        results = []

        for version in reversed(versions):
            if version not in self._migrations:
                logger.warning(f"Migration {version} not found, skipping")
                continue

            migration = self._migrations[version]
            result = await self._rollback_migration(migration)
            results.append(result)

            if not result.get('success', False):
                logger.error(f"Rollback of {migration.name} failed, stopping")
                break

        logger.info(f"Rollback complete: {len([r for r in results if r['success']])} rolled back")
        return results

    async def _rollback_migration(self, migration: Migration) -> Dict[str, Any]:
        """
        Rollback a single migration

        Args:
            migration: Migration to rollback

        Returns:
            Result dict with success status
        """
        logger.info(f"Rolling back migration: {migration.name}")

        result = {
            'version': migration.version,
            'name': migration.name,
            'success': False,
            'error': None
        }

        try:
            await migration.down()

            # Remove from schema_migrations
            async with self.repo.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM schema_migrations WHERE version = $1",
                    migration.version
                )

            result['success'] = True
            migration.log("Rolled back successfully")

        except NotImplementedError:
            result['error'] = "Rollback not supported"
            migration.log("Rollback not supported", "warning")

        except Exception as e:
            result['error'] = str(e)
            migration.log(f"Rollback failed: {e}", "error")
            logger.error(f"Rollback of {migration.name} failed: {e}")

        return result

    async def status(self) -> Dict[str, Any]:
        """
        Get migration status

        Returns:
            Status dict with applied and pending migrations
        """
        applied = await self.get_applied_migrations()
        pending = await self.get_pending_migrations()

        return {
            'applied_count': len(applied),
            'pending_count': len(pending),
            'applied': list(applied.keys()),
            'pending': [m.version for m in pending],
            'current_version': list(applied.keys())[-1] if applied else None,
        }

    async def create_migration(
        self,
        version: str,
        description: str,
        author: str = "Unknown"
    ) -> None:
        """
        Create a new migration file

        Args:
            version: Migration version (YYYY.MMDD.patch format)
            description: Migration description
            author: Author name
        """
        # Sanitize description for filename
        desc_slug = description.lower().replace(' ', '_').replace('-', '_')
        filename = f"migration_{version}_{desc_slug}.py"
        filepath = Path(self.migrations_path) / filename

        template = f'''"""
Migration: {description}

Author: {author}
Version: {version}
"""

from libs.db_repo.migrations import Migration
import logging

logger = logging.getLogger(__name__)


class Migration_{version.replace('.', '')}(Migration):
    \"""Migration {version}: {description}""""

    version = "{version}"
    description = "{description}"
    author = "{author}"
    depends_on = []

    async def up(self) -> None:
        \"""Apply migration""""
        async with self.pool.acquire() as conn:
            # TODO: Implement migration
            pass

    async def down(self) -> None:
        \"""Rollback migration""""
        async with self.pool.acquire() as conn:
            # TODO: Implement rollback
            raise NotImplementedError("Rollback not implemented")
'''

        filepath.write_text(template)
        logger.info(f"Created migration file: {filename}")
