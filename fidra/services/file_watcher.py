"""File watcher service for detecting database changes.

Uses watchdog to monitor the database file for external modifications.
"""

import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal, QMetaObject, Qt, Q_ARG
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class DatabaseFileHandler(FileSystemEventHandler):
    """Handler for database file system events."""

    def __init__(self, file_path: Path, callback: Callable[[], None]):
        """Initialize handler.

        Args:
            file_path: Path to the database file to watch
            callback: Function to call when file is modified
        """
        super().__init__()
        self._file_path = file_path
        self._callback = callback
        self._last_modified = 0.0
        self._debounce_seconds = 0.5  # Debounce rapid events

        # SQLite can use WAL mode, which writes to separate files
        # Watch for: main.db, main.db-wal, main.db-shm, main.db-journal
        db_name = self._file_path.name
        self._watched_names = {
            db_name,
            f"{db_name}-wal",
            f"{db_name}-shm",
            f"{db_name}-journal",
        }

    def _is_relevant_file(self, event_path: Path) -> bool:
        """Check if the event is for a relevant database file."""
        return event_path.name in self._watched_names

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        event_path = Path(event.src_path)
        if self._is_relevant_file(event_path):
            current_time = time.time()
            if current_time - self._last_modified > self._debounce_seconds:
                self._last_modified = current_time
                self._callback()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events (WAL files may be created)."""
        if event.is_directory:
            return

        event_path = Path(event.src_path)
        if self._is_relevant_file(event_path):
            current_time = time.time()
            if current_time - self._last_modified > self._debounce_seconds:
                self._last_modified = current_time
                self._callback()


class FileWatcherService(QObject):
    """Service for watching database file changes.

    Emits a Qt signal when the watched file is modified externally.
    Uses debouncing to avoid rapid-fire events.

    Example:
        >>> watcher = FileWatcherService()
        >>> watcher.file_changed.connect(on_database_changed)
        >>> watcher.start_watching(Path("fidra.db"))
    """

    file_changed = Signal()  # Emitted when watched file changes
    _trigger_debounce = Signal()  # Internal signal for thread-safe timer start

    def __init__(self, parent: Optional[QObject] = None):
        """Initialize file watcher service.

        Args:
            parent: Optional parent QObject
        """
        super().__init__(parent)
        self._observer: Optional[Observer] = None
        self._watched_path: Optional[Path] = None
        self._handler: Optional[DatabaseFileHandler] = None

        # Timer for debouncing Qt signal emission
        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(500)  # 500ms debounce
        self._emit_timer.timeout.connect(self._emit_file_changed)
        self._pending_emit = False

        # Connect internal signal for thread-safe timer triggering
        self._trigger_debounce.connect(self._start_debounce_timer, Qt.QueuedConnection)

    def start_watching(self, file_path: Path) -> None:
        """Start watching a file for changes.

        Args:
            file_path: Path to the file to watch
        """
        # Stop any existing watcher
        self.stop_watching()

        self._watched_path = file_path.resolve()

        # Create handler and observer
        self._handler = DatabaseFileHandler(
            self._watched_path,
            self._on_file_changed
        )
        self._observer = Observer()

        # Watch the directory containing the file
        watch_dir = str(self._watched_path.parent)
        self._observer.schedule(self._handler, watch_dir, recursive=False)
        self._observer.start()

    def stop_watching(self) -> None:
        """Stop watching the current file."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
            self._handler = None
            self._watched_path = None

    def _on_file_changed(self) -> None:
        """Handle file change from watchdog (called from watchdog thread)."""
        # Use signal to marshal to Qt thread (thread-safe)
        self._pending_emit = True
        self._trigger_debounce.emit()

    def _start_debounce_timer(self) -> None:
        """Start the debounce timer (called on Qt thread via signal)."""
        if not self._emit_timer.isActive():
            self._emit_timer.start()

    def _emit_file_changed(self) -> None:
        """Emit the file_changed signal on the Qt thread."""
        if self._pending_emit:
            self._pending_emit = False
            self.file_changed.emit()

    @property
    def watched_path(self) -> Optional[Path]:
        """Get the currently watched file path."""
        return self._watched_path

    @property
    def is_watching(self) -> bool:
        """Check if currently watching a file."""
        return self._observer is not None and self._observer.is_alive()
