"""PostgreSQL connection pool management using asyncpg.

Provides connection pooling for cloud PostgreSQL databases (Supabase, self-hosted, etc.)
with automatic retry logic and connection state management.
"""

import asyncio
import logging
from typing import Callable, Optional, TYPE_CHECKING, TypeVar

import asyncpg

from fidra.data.resilience import (
    classify_error,
    ErrorCategory,
    get_user_message,
    with_retry,
)

if TYPE_CHECKING:
    from fidra.domain.settings import CloudServerConfig

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CloudConnection:
    """Manages asyncpg connection pool for PostgreSQL databases.

    Handles connection lifecycle, pooling, reconnection, and automatic retry
    for transient failures.

    Example:
        >>> config = CloudServerConfig(
        ...     id="abc123",
        ...     name="My Server",
        ...     db_connection_string="postgresql://..."
        ... )
        >>> conn = CloudConnection(config)
        >>> await conn.connect()
        >>> pool = conn.pool
        >>> # Use pool for queries
        >>> await conn.close()
    """

    def __init__(self, config: "CloudServerConfig"):
        """Initialize connection manager.

        Args:
            config: Cloud server configuration with connection string and pool settings
        """
        self._config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._is_healthy = False

        # Callbacks for connection state changes
        self.on_connection_lost: Optional[Callable[[], None]] = None
        self.on_connection_restored: Optional[Callable[[], None]] = None
        self.on_retry: Optional[Callable[[int, float], None]] = None

    @property
    def config(self) -> "CloudServerConfig":
        """Get the server configuration."""
        return self._config

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
        """Check if pool exists (may not be healthy)."""
        return self._pool is not None

    @property
    def is_healthy(self) -> bool:
        """Check if connection is healthy (last health check passed)."""
        return self._is_healthy and self._pool is not None

    async def connect(self) -> None:
        """Create connection pool with automatic retry.

        Raises:
            ValueError: If connection string not configured
            asyncpg.PostgresError: If connection fails after retries
        """
        if not self._config.db_connection_string:
            raise ValueError("Database connection string not configured")

        async def do_connect():
            self._pool = await asyncpg.create_pool(
                self._config.db_connection_string,
                min_size=self._config.pool_min_size,
                max_size=self._config.pool_max_size,
                command_timeout=30,
                # Disable prepared statements for connection poolers
                statement_cache_size=0,
            )

        def on_retry_callback(attempt: int, delay: float, error: Exception):
            logger.info(f"Connection attempt {attempt} failed, retrying in {delay:.1f}s")
            if self.on_retry:
                self.on_retry(attempt, delay)

        await with_retry(
            do_connect,
            max_retries=3,
            initial_delay=1.0,
            max_delay=10.0,
            on_retry=on_retry_callback,
        )

        self._is_healthy = True
        logger.info("Connection pool created successfully")

    async def close(self, timeout: Optional[float] = None) -> None:
        """Close connection pool gracefully.

        Args:
            timeout: Optional timeout in seconds. If close doesn't complete
                     within timeout, the pool is forcefully terminated.
        """
        if self._pool:
            pool = self._pool
            self._pool = None  # Clear reference first to prevent reuse
            self._is_healthy = False

            try:
                if timeout:
                    await asyncio.wait_for(pool.close(), timeout=timeout)
                else:
                    await pool.close()
                logger.info("Connection pool closed gracefully")
            except asyncio.TimeoutError:
                logger.warning(f"Pool close timed out after {timeout}s, terminating")
                pool.terminate()
                logger.info("Connection pool terminated")
            except Exception as e:
                logger.warning(f"Pool close failed: {e}, terminating")
                try:
                    pool.terminate()
                except Exception:
                    pass  # Already failed, nothing more to do

    async def health_check(self) -> bool:
        """Check if connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self._pool:
            self._is_healthy = False
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            if not self._is_healthy:
                # Connection restored
                self._is_healthy = True
                logger.info("Connection health restored")
                if self.on_connection_restored:
                    self.on_connection_restored()
            return True
        except Exception as e:
            if self._is_healthy:
                # Connection lost
                self._is_healthy = False
                logger.warning(f"Connection health check failed: {e}")
                if self.on_connection_lost:
                    self.on_connection_lost()
            return False

    async def reconnect(self) -> None:
        """Close and reconnect the pool with retry.

        Uses a short timeout on close to avoid hanging on stuck connections.
        """
        logger.info("Reconnect: closing old pool...")
        # Use short timeout - if pool is stuck, terminate it
        await self.close(timeout=2.0)
        logger.info("Reconnect: old pool closed, creating new pool...")
        await self.connect()
        logger.info("Reconnect: new pool created, verifying connection...")

        # Verify the new pool works
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("Reconnect: connection verified successfully")
        except Exception as e:
            logger.error(f"Reconnect: verification failed: {e}")
            raise

        if self.on_connection_restored:
            logger.info("Reconnect: calling on_connection_restored callback")
            self.on_connection_restored()

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        max_retries: int = 3,
    ) -> T:
        """Execute an operation with automatic retry on transient failures.

        Args:
            operation: Async callable that uses the connection pool
            max_retries: Maximum retry attempts

        Returns:
            Result of the operation

        Raises:
            Exception: If operation fails after all retries or with permanent error
        """
        was_healthy = self._is_healthy

        def on_retry_callback(attempt: int, delay: float, error: Exception):
            logger.warning(f"Operation failed (attempt {attempt}), retrying: {error}")
            if self.on_retry:
                self.on_retry(attempt, delay)

        try:
            result = await with_retry(
                operation,
                max_retries=max_retries,
                initial_delay=0.5,
                max_delay=5.0,
                on_retry=on_retry_callback,
            )
            # Operation succeeded
            if not was_healthy:
                self._is_healthy = True
                if self.on_connection_restored:
                    self.on_connection_restored()
            return result

        except Exception as e:
            # Check if this is a connection failure
            category = classify_error(e)
            if category == ErrorCategory.TRANSIENT and was_healthy:
                self._is_healthy = False
                if self.on_connection_lost:
                    self.on_connection_lost()

            # Re-raise with user-friendly message available
            raise

    def get_user_error_message(self, exception: Exception) -> str:
        """Get a user-friendly error message for an exception.

        Args:
            exception: The exception to describe

        Returns:
            Human-readable error message
        """
        return get_user_message(exception)
