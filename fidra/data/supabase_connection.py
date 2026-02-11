"""Supabase/PostgreSQL connection pool management using asyncpg."""

from typing import Optional, TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from fidra.domain.settings import SupabaseSettings


class SupabaseConnection:
    """Manages asyncpg connection pool for Supabase PostgreSQL.

    Handles connection lifecycle, pooling, and reconnection.

    Example:
        >>> config = SupabaseSettings(db_connection_string="postgresql://...")
        >>> conn = SupabaseConnection(config)
        >>> await conn.connect()
        >>> pool = conn.pool
        >>> # Use pool for queries
        >>> await conn.close()
    """

    def __init__(self, config: "SupabaseSettings"):
        """Initialize connection manager.

        Args:
            config: Supabase settings with connection string and pool config
        """
        self._config = config
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool.

        Raises:
            RuntimeError: If not connected
        """
        if self._pool is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Check if pool is connected and healthy."""
        return self._pool is not None

    async def connect(self) -> None:
        """Create connection pool.

        Raises:
            ValueError: If connection string not configured
            asyncpg.PostgresError: If connection fails
        """
        if not self._config.db_connection_string:
            raise ValueError("Database connection string not configured")

        self._pool = await asyncpg.create_pool(
            self._config.db_connection_string,
            min_size=self._config.pool_min_size,
            max_size=self._config.pool_max_size,
            command_timeout=30,
            # Disable prepared statements for Supabase transaction pooler (Supavisor)
            statement_cache_size=0,
        )

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def health_check(self) -> bool:
        """Check if connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self._pool:
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def reconnect(self) -> None:
        """Close and reconnect the pool."""
        await self.close()
        await self.connect()
