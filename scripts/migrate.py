#!/usr/bin/env python3
"""
Migration CLI Tool

Manage database migrations from command line.

Usage:
    python scripts/migrate.py status
    python scripts/migrate.py migrate
    python scripts/migrate.py rollback --steps 1
    python scripts/migrate.py create --version 2024.02.01 --description "Add indexes"
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from libs.db_repo import TimescaleDBRepository
from libs.db_repo.migrations import MigrationRunner
from libs.common.config import DatabaseConfig


def print_section(title: str) -> None:
    """Print section header"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def print_success(msg: str) -> None:
    """Print success message"""
    print(f"✓ {msg}")


def print_error(msg: str) -> None:
    """Print error message"""
    print(f"✗ {msg}")


def print_warning(msg: str) -> None:
    """Print warning message"""
    print(f"⚠ {msg}")


async def status(config: DatabaseConfig) -> int:
    """Show migration status"""
    repo = TimescaleDBRepository(config)
    await repo.connect()

    try:
        runner = MigrationRunner(repo)
        status_info = await runner.status()

        print_section("MIGRATION STATUS")

        print(f"\nApplied Migrations: {status_info['applied_count']}")
        if status_info['applied']:
            for version in status_info['applied']:
                print(f"  • {version}")

        print(f"\nPending Migrations: {status_info['pending_count']}")
        if status_info['pending']:
            for version in status_info['pending']:
                print(f"  • {version}")

        if status_info['current_version']:
            print_success(f"Current version: {status_info['current_version']}")
        else:
            print_warning("No migrations applied yet")

        return 0

    except Exception as e:
        print_error(f"Failed to get status: {e}")
        return 1
    finally:
        await repo.close()


async def migrate(
    config: DatabaseConfig,
    target: str = None,
    dry_run: bool = False,
    steps: int = 0
) -> int:
    """Run pending migrations"""
    repo = TimescaleDBRepository(config)
    await repo.connect()

    try:
        runner = MigrationRunner(repo)

        print_section("MIGRATE")

        if dry_run:
            print_warning("DRY RUN MODE - No changes will be applied")

        results = await runner.migrate(
            target_version=target,
            dry_run=dry_run,
            steps=steps
        )

        print(f"\n{'Version':<15} {'Name':<30} {'Status':<10}")
        print("-" * 60)

        for result in results:
            status = "✓ Success" if result['success'] else "✗ Failed"
            print(f"{result['version']:<15} {result['name'][:30]:<30} {status:<10}")
            if result.get('error'):
                print(f"  Error: {result['error']}")

        success_count = sum(1 for r in results if r['success'])

        if dry_run:
            print(f"\nDry run complete: {success_count} migrations would be applied")
        else:
            print_success(f"Migration complete: {success_count} migrations applied")

        return 0 if all(r['success'] for r in results) else 1

    except Exception as e:
        print_error(f"Migration failed: {e}")
        return 1
    finally:
        await repo.close()


async def rollback(
    config: DatabaseConfig,
    target: str = None,
    steps: int = 1
) -> int:
    """Rollback migrations"""
    repo = TimescaleDBRepository(config)
    await repo.connect()

    try:
        runner = MigrationRunner(repo)

        print_section("ROLLBACK")
        print_warning("This will revert recent migrations")

        results = await runner.rollback(
            target_version=target,
            steps=steps
        )

        print(f"\n{'Version':<15} {'Name':<30} {'Status':<10}")
        print("-" * 60)

        for result in results:
            status = "✓ Success" if result['success'] else "✗ Failed"
            print(f"{result['version']:<15} {result['name'][:30]:<30} {status:<10}")
            if result.get('error'):
                print(f"  Error: {result['error']}")

        success_count = sum(1 for r in results if r['success'])
        print_success(f"Rollback complete: {success_count} migrations rolled back")

        return 0 if all(r['success'] for r in results) else 1

    except Exception as e:
        print_error(f"Rollback failed: {e}")
        return 1
    finally:
        await repo.close()


async def create_migration(
    version: str,
    description: str,
    author: str = "Unknown"
) -> int:
    """Create a new migration file"""
    try:
        from libs.db_repo.migrations import MigrationRunner

        # Create a dummy runner just to access the create_migration method
        runner = MigrationRunner(None)
        await runner.create_migration(version, description, author)

        print_success(f"Created migration {version}: {description}")
        print(f"Edit the migration file to implement up() and down() methods")

        return 0

    except Exception as e:
        print_error(f"Failed to create migration: {e}")
        return 1


async def refresh(config: DatabaseConfig) -> int:
    """Refresh all materialized views"""
    repo = TimescaleDBRepository(config)
    await repo.connect()

    try:
        print_section("REFRESH MATERIALIZED VIEWS")

        views = [
            "market_features_5m",
            "market_features_15m",
            "market_features_30m",
            "market_features_1h",
            "market_features_4h",
            "market_features_1d",
            "market_features_1w"
        ]

        async with repo.pool.acquire() as conn:
            for view in views:
                try:
                    await conn.execute(f"REFRESH MATERIALIZED VIEW {view};")
                    print_success(f"Refreshed {view}")
                except Exception as e:
                    print_error(f"Failed to refresh {view}: {e}")

        return 0

    except Exception as e:
        print_error(f"Refresh failed: {e}")
        return 1
    finally:
        await repo.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Tradebase Database Migration Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show migration status
  python scripts/migrate.py status

  # Run all pending migrations
  python scripts/migrate.py migrate

  # Run one migration (dry run)
  python scripts/migrate.py migrate --steps 1 --dry-run

  # Rollback last migration
  python scripts/migrate.py rollback

  # Rollback 3 migrations
  python scripts/migrate.py rollback --steps 3

  # Create new migration
  python scripts/migrate.py create --version 2024.02.01 --description "Add user preferences table"
        """
    )

    parser.add_argument(
        "--db-host",
        default="localhost",
        help="Database host (default: localhost)"
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=5432,
        help="Database port (default: 5432)"
    )
    parser.add_argument(
        "--db-name",
        default="tradebase",
        help="Database name (default: tradebase)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Status command
    subparsers.add_parser("status", help="Show migration status")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run pending migrations")
    migrate_parser.add_argument("--target", help="Target version to stop at")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    migrate_parser.add_argument("--steps", type=int, default=0, help="Number of migrations to run")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument("--target", help="Target version to rollback to")
    rollback_parser.add_argument("--steps", type=int, default=1, help="Number of migrations to rollback")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create new migration file")
    create_parser.add_argument("--version", required=True, help="Migration version (YYYY.MMDD.patch)")
    create_parser.add_argument("--description", required=True, help="Migration description")
    create_parser.add_argument("--author", default="Tradebase Team", help="Author name")

    # Refresh command
    subparsers.add_parser("refresh", help="Refresh all materialized views")

    args = parser.parse_args()

    # Build config from args
    config = DatabaseConfig(
        host=args.db_host,
        port=args.db_port,
        database=args.db_name
    )

    # Execute command
    if args.command == "status":
        return asyncio.run(status(config))
    elif args.command == "migrate":
        return asyncio.run(migrate(config, args.target, args.dry_run, args.steps))
    elif args.command == "rollback":
        return asyncio.run(rollback(config, args.target, args.steps))
    elif args.command == "create":
        return asyncio.run(create_migration(args.version, args.description, args.author))
    elif args.command == "refresh":
        return asyncio.run(refresh(config))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
