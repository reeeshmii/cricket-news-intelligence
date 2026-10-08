"""Single-crawl lock + status file, shared by the loop, manual runs and (later) refresh triggers."""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import settings

LOCK_PATH = settings.DATA_DIR / "crawler.lock"
STATUS_PATH = settings.DATA_DIR / "crawler_status.json"
STALE_AFTER_SECONDS = 3 * 3600      # a lock older than this is from a crashed run


class CrawlerBusy(Exception):
    pass


@contextmanager
def crawl_lock(path: Path | str = LOCK_PATH, stale_after: float = STALE_AFTER_SECONDS):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - path.stat().st_mtime < stale_after:
            raise CrawlerBusy(f"another crawl is running (lock: {path})")
        path.unlink(missing_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise CrawlerBusy(f"another crawl is running (lock: {path})")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}))
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def update_status(path: Path | str = STATUS_PATH, **fields) -> dict:
    """Merge fields into the status JSON (atomic write). Readable by a future API's /status."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    status = json.loads(path.read_text("utf-8")) if path.exists() else {}
    status.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return status
