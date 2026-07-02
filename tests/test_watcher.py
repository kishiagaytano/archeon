"""Tests for the file watcher."""

from __future__ import annotations

from archeon.lifecycle.watcher import LifecycleWatcher

from lifecycle_fixtures import fresh_state


def test_polling_watcher_detects_deletion(tmp_path) -> None:
    fresh_state()
    watch_dir = tmp_path / "repo"
    watch_dir.mkdir()
    target = watch_dir / "storage.py"
    target.write_text("session store", encoding="utf-8")

    deleted: list[str] = []

    def on_delete(path: str) -> None:
        deleted.append(path)

    watcher = LifecycleWatcher(watch_dir, on_delete=on_delete)
    watcher._start_polling(blocking=False)
    import time

    time.sleep(0.2)
    target.unlink()
    time.sleep(1.5)
    watcher.stop()

    assert deleted == [str(target)]
