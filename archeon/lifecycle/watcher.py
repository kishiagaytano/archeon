"""File watcher that triggers forget() when source files are deleted."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .lifecycle import handle_file_deletion
from .logger import get_logger

logger = get_logger(__name__)

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    _WATCHDOG_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    FileSystemEventHandler = object  # type: ignore[misc, assignment]
    _WATCHDOG_AVAILABLE = False


class _DeletionHandler(FileSystemEventHandler):
    def __init__(self, on_delete: Callable[[str], None]) -> None:
        self._on_delete = on_delete

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._on_delete(event.src_path)


class LifecycleWatcher:
    """Watch a directory and call ``handle_file_deletion`` on file deletes."""

    def __init__(
        self,
        watch_path: str | Path,
        *,
        on_delete: Callable[[str], None] | None = None,
    ) -> None:
        self.watch_path = Path(watch_path)
        self._on_delete = on_delete or handle_file_deletion
        self._observer: Optional[Observer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._known_files: set[str] = set()

    def start(self, *, blocking: bool = False) -> None:
        """Start watching. Uses watchdog when installed, else polling."""
        if not self.watch_path.exists():
            raise FileNotFoundError(f"Watch path does not exist: {self.watch_path}")

        if _WATCHDOG_AVAILABLE:
            self._start_watchdog(blocking=blocking)
        else:
            logger.warning(
                "watchdog not installed; using polling watcher for %s",
                self.watch_path,
            )
            self._start_polling(blocking=blocking)

    def stop(self) -> None:
        """Stop the watcher."""
        self._stop_event.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _start_watchdog(self, *, blocking: bool) -> None:
        handler = _DeletionHandler(self._on_delete)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.watch_path), recursive=True)
        self._observer.start()
        logger.info("Lifecycle watcher started (watchdog): %s", self.watch_path)
        if blocking:
            try:
                while not self._stop_event.wait(1):
                    pass
            finally:
                self.stop()

    def _start_polling(self, *, blocking: bool) -> None:
        self._known_files = {
            str(p) for p in self.watch_path.rglob("*") if p.is_file()
        }

        def poll() -> None:
            while not self._stop_event.is_set():
                current = {
                    str(p) for p in self.watch_path.rglob("*") if p.is_file()
                }
                removed = self._known_files - current
                for path in removed:
                    logger.info("Detected deletion (poll): %s", path)
                    self._on_delete(path)
                self._known_files = current
                time.sleep(1)

        self._thread = threading.Thread(target=poll, daemon=True)
        self._thread.start()
        logger.info("Lifecycle watcher started (polling): %s", self.watch_path)
        if blocking:
            try:
                while not self._stop_event.wait(1):
                    pass
            finally:
                self.stop()
