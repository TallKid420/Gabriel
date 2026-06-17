# daemon/pid_lock.py
import os, json
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = _PROJECT_ROOT / "run" / "daemon.pid"
DAEMON_PORT = 8765

def write_lock(pid: int, port: int) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps({"pid": pid, "port": port}))

def read_lock() -> dict | None:
    if not LOCK_FILE.exists():
        return None
    try:
        return json.loads(LOCK_FILE.read_text())
    except Exception:
        return None

def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)   # signal 0 = existence check
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False

def clear_lock():
    LOCK_FILE.unlink(missing_ok=True)

def get_running_daemon() -> dict | None:
    """Returns {pid, port} if daemon is alive, else None."""
    info = read_lock()
    if info and is_alive(info["pid"]):
        return info
    clear_lock()
    return None