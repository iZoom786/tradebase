"""
Base migration class for database schema changes

All migrations must inherit from Migration and implement:
- up(): Apply the migration
- down(): Rollback the migration
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Migration(ABC):
    """
    Base class for database migrations

    Each migration represents a single schema change and should be
    atomic and reversible.
    """

    # Migration version (semantic versioning: YYYY.MMDD.patch)
    version: str = "0000.00.00"

    # Migration description
    description: str = "Base migration"

    # Author of the migration
    author: str = "Unknown"

    # Dependencies on other migrations (versions that must run first)
    depends_on: list[str] = []

    def __init__(self, pool=None):
        """
        Initialize migration

        Args:
            pool: Optional asyncpg connection pool
        """
        self.pool = pool
        self.applied_at: Optional[datetime] = None

    @abstractmethod
    async def up(self) -> None:
        """
        Apply the migration

        This method should contain all SQL statements needed to
        apply the schema change.
        """
        pass

    @abstractmethod
    async def down(self) -> None:
        """
        Rollback the migration

        This method should reverse the changes made in up().
        If rollback is not possible, raise NotImplementedError.
        """
        pass

    async def validate(self) -> bool:
        """
        Validate that the migration can be applied

        Called before up() to check prerequisites.
        Returns True if validation passes.

        Returns:
            True if migration can proceed
        """
        return True

    def __repr__(self) -> str:
        return f"Migration(version={self.version}, description={self.description})"

    @property
    def name(self) -> str:
        """Generate a migration name from version and description"""
        desc_slug = self.description.lower().replace(' ', '_').replace('-', '_')
        return f"{self.version}_{desc_slug}"

    def log(self, message: str, level: str = "info") -> None:
        """Log migration message"""
        getattr(logger, level)(f"[{self.name}] {message}")
