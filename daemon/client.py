# daemon/client.py
import time
import httpx
from daemon.pid_lock import get_running_daemon
from daemon.launcher import launch_daemon

_STARTUP_TIMEOUT_SEC = 10.0
_STARTUP_POLL_INTERVAL = 0.25

class DaemonClient:
    """UI-side proxy. Connects to running daemon or starts one."""

    def __init__(self):
        self._base: str | None = None

    def _base_url(self) -> str | None:
        # Never cache — always re-check lockfile so reconnection works
        # after daemon restarts without needing a UI restart.
        info = get_running_daemon()
        return f"http://127.0.0.1:{info['port']}" if info else None

    def get_config(self) -> dict:
        base = self._base_url()
        if not base:
            return {}
        try:
            r = httpx.get(f"{base}/daemon/config", timeout=3)
            return r.json().get("config", {})
        except Exception:
            return {}

    def patch_config(self, **kwargs) -> dict:
        base = self._base_url()
        if not base:
            return {}
        try:
            r = httpx.patch(f"{base}/daemon/config", json=kwargs, timeout=3)
            return r.json().get("config", {})
        except Exception as e:
            return {"error": str(e)}

    def _ensure_connected(self) -> str:
        if self._base:
            return self._base
        info = get_running_daemon()
        if not info:
            raise RuntimeError("Daemon not running. Call start() first.")
        self._base = f"http://127.0.0.1:{info['port']}"
        return self._base

    def start(self) -> dict:
        info = get_running_daemon()

        if info:
            return {"started": False, "message": "Already running", **info}
        
        pid = launch_daemon()

        deadline = time.time() + _STARTUP_TIMEOUT_SEC
        while time.time() < deadline:
            info = get_running_daemon()
            if info:
                self._base = f"http://127.0.0.1:{info['port']}"
                return {"started": True, "pid": pid, "port": info["port"]}
            time.sleep(_STARTUP_POLL_INTERVAL)

        return {"started": False, "error": "Daemon did not become ready in time"}

    def stop(self) -> dict:
        try:
            r = httpx.post(f"{self._base}/daemon/stop", timeout=5)
            self._base = None
            return r.json()
        except Exception as e:
            return {"stopped": False, "error": str(e)}

    def status(self) -> dict:
        try:
            base = self._ensure_connected()
            r = httpx.get(f"{base}/daemon/status", timeout=3)
            return r.json()["status", {}]
        except RuntimeError:
            return {"running": False, "tick_count": 0, "last_results": []}
        except Exception as e:
            return {"running": False, "error": f"Daemon unreachable: {str(e)}"}

    def is_reachable(self) -> bool:
        try:
            base = self._ensure_connected()
            httpx.get(f"{base}/health", timeout=2).raise_for_status()
            return True
        except RuntimeError:
            return False
        except Exception:
            return False