"""Real-time change listener using PostgreSQL LISTEN/NOTIFY.

Listens for data changes on synced tables and triggers cache refresh
so changes from other devices appear in real time.

Uses a dedicated asyncpg connection (not from the pool) to avoid
affecting pool sizing. Notifications are debounced to batch rapid changes.

IMPORTANT: LISTEN/NOTIFY does not work through connection poolers
(PgBouncer, Supavisor) in transaction mode. This module automatically
detects Supabase pooler URLs and derives the direct connection URL.
"""

import asyncio
import json
import logging
from urllib.parse import urlparse, urlunparse
from typing import Optional, TYPE_CHECKING

import asyncpg
import qasync
from PySide6.QtCore import QObject, QTimer, Signal

if TYPE_CHECKING:
    from fidra.data.cloud_connection import CloudConnection

logger = logging.getLogger(__name__)

# Channel name for all fidra change notifications
NOTIFY_CHANNEL = "fidra_changes"

# SQL to create the notify trigger function (idempotent)
_CREATE_NOTIFY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION fidra_notify_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'fidra_changes',
        json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP
        )::text
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""

# SQL template for creating a trigger on a table (idempotent)
_CREATE_TRIGGER_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'fidra_notify_{table}'
    ) THEN
        CREATE TRIGGER fidra_notify_{table}
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION fidra_notify_change();
    END IF;
END $$;
"""

# Tables that are synced and should be watched for changes
WATCHED_TABLES = ("transactions", "planned_templates", "sheets", "categories")


def _get_direct_dsn(dsn: str) -> str:
    """Convert a pooler connection string to session mode if needed.

    Supabase pooler URLs use port 6543 for transaction mode, which
    silently drops LISTEN/NOTIFY. Port 5432 on the same host uses
    session mode, which supports LISTEN/NOTIFY.

    Non-pooler URLs are returned unchanged.
    """
    parsed = urlparse(dsn)
    port = parsed.port

    # Detect Supabase transaction-mode pooler (port 6543)
    if port != 6543:
        return dsn

    # Switch to session mode: same host, port 5432
    # Replace ":6543" with ":5432" in netloc
    new_netloc = parsed.netloc.replace(":6543", ":5432")
    direct = urlunparse((
        parsed.scheme,
        new_netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    host = parsed.hostname or "pooler"
    print(f"[LISTEN] Using session mode: {host}:5432")
    return direct


class ChangeListener(QObject):
    """Listens for PostgreSQL NOTIFY events and triggers cache refresh.

    Uses a dedicated connection (not from the pool) so that pool sizing
    is unaffected. Debounces rapid notifications to avoid redundant refreshes.

    If the listener fails to start or loses its connection, the app continues
    to work normally -- it just won't get real-time updates from other devices.
    """

    tables_changed = Signal(object)   # set[str] of changed table names
    listener_started = Signal()
    listener_stopped = Signal()

    # Internal signal to marshal notification callback to Qt thread
    _trigger_debounce = Signal()

    def __init__(
        self,
        cloud_connection: "CloudConnection",
        debounce_ms: int = 1000,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._cloud_connection = cloud_connection
        self._debounce_ms = debounce_ms

        self._listener_conn: Optional[asyncpg.Connection] = None
        self._dirty_tables: set[str] = set()
        self._is_running = False
        self._self_test_received = False

        # Debounce timer: collects rapid notifications into one refresh
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(debounce_ms)
        self._debounce_timer.timeout.connect(self._on_debounce_fired)

        # Thread-safe bridge: notification callback → Qt thread
        self._trigger_debounce.connect(self._restart_debounce_timer)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start listening for changes. Fails silently on error."""
        if self._is_running:
            return

        try:
            # Use direct connection (not pooler) for LISTEN/NOTIFY support
            dsn = _get_direct_dsn(self._cloud_connection.config.db_connection_string)
            self._listener_conn = await asyncpg.connect(
                dsn, timeout=10, statement_cache_size=0,
            )

            # Install triggers (idempotent, uses the listener's connection)
            await self._ensure_triggers()

            # Start listening
            await self._listener_conn.add_listener(
                NOTIFY_CHANNEL, self._on_notification,
            )

            # Self-test: verify LISTEN/NOTIFY actually works
            if not await self._self_test():
                print("[LISTEN] Self-test failed - NOTIFY not received (pooler issue?)")
                logger.warning("LISTEN/NOTIFY self-test failed")
                await self._cleanup()
                return

            self._is_running = True
            logger.info("Change listener started")
            print("[LISTEN] Change listener started (verified)")
            self.listener_started.emit()

        except Exception as e:
            logger.warning(f"Failed to start change listener: {e}")
            print(f"[LISTEN] Failed to start: {e}")
            await self._cleanup()

    async def stop(self) -> None:
        """Stop listening and close the dedicated connection."""
        self._is_running = False
        self._debounce_timer.stop()
        self._dirty_tables.clear()

        if self._listener_conn:
            try:
                await self._listener_conn.remove_listener(
                    NOTIFY_CHANNEL, self._on_notification,
                )
            except Exception:
                pass  # Connection may already be closed

        await self._cleanup()
        logger.info("Change listener stopped")
        self.listener_stopped.emit()

    async def restart(self) -> None:
        """Restart the listener (e.g. after reconnection)."""
        await self.stop()
        await self.start()

    # ------------------------------------------------------------------
    # Trigger installation
    # ------------------------------------------------------------------

    async def _ensure_triggers(self) -> None:
        """Create notify function and triggers if they don't exist."""
        conn = self._listener_conn
        await conn.execute(_CREATE_NOTIFY_FUNCTION_SQL)

        for table in WATCHED_TABLES:
            await conn.execute(_CREATE_TRIGGER_SQL.format(table=table))

        logger.info(f"Ensured NOTIFY triggers on {list(WATCHED_TABLES)}")
        print(f"[LISTEN] Ensured triggers on {list(WATCHED_TABLES)}")

    # ------------------------------------------------------------------
    # Self-test
    # ------------------------------------------------------------------

    async def _self_test(self) -> bool:
        """Send a test NOTIFY and verify it arrives. Returns True if working."""
        self._self_test_received = False
        test_payload = '{"table":"_test","op":"TEST"}'
        await self._listener_conn.execute(
            f"NOTIFY {NOTIFY_CHANNEL}, '{test_payload}'"
        )

        # Wait up to 2 seconds for the notification to arrive
        for _ in range(20):
            await asyncio.sleep(0.1)
            if self._self_test_received:
                return True

        return False

    # ------------------------------------------------------------------
    # Notification handling
    # ------------------------------------------------------------------

    def _on_notification(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Handle NOTIFY event (called on asyncpg's internal thread).

        Only writes to a set and emits a Qt signal -- both are thread-safe.
        """
        try:
            data = json.loads(payload)
            table = data.get("table", "")

            # Handle self-test notification
            if table == "_test":
                self._self_test_received = True
                return

            if table in WATCHED_TABLES:
                self._dirty_tables.add(table)
                self._trigger_debounce.emit()
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid notification payload: {payload} ({e})")

    def _restart_debounce_timer(self) -> None:
        """Restart the debounce timer (runs on Qt thread via signal)."""
        self._debounce_timer.start()

    @qasync.asyncSlot()
    async def _on_debounce_fired(self) -> None:
        """Debounce timer expired -- emit tables_changed with dirty set."""
        if not self._dirty_tables:
            return

        changed = self._dirty_tables.copy()
        self._dirty_tables.clear()

        logger.info(f"Remote changes detected: {changed}")
        print(f"[LISTEN] Remote changes: {changed}")
        self.tables_changed.emit(changed)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        """Close the listener connection safely."""
        if self._listener_conn:
            try:
                await self._listener_conn.close(timeout=2.0)
            except Exception:
                pass
            self._listener_conn = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self._listener_conn is not None
