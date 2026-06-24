from __future__ import annotations

import signal
import threading
import time, os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from daemon.pid_lock import _PROJECT_ROOT
from agents.types.daemon_agent import DaemonAgent
from agents.executor import AgentExecutor, AgentExecutionResult
from config.config_manager import ConfigManager


@dataclass
class DaemonConfig:
    name: str = "sample-daemon"
    tick_interval_sec: float = 1.0
    shutdown_timeout_sec: float = 5.0
    config_path: str = "config/agents.yaml"
    metadata: dict[str, Any] = field(default_factory=dict)

class ServerDaemon:
    def __init__(self, config: DaemonConfig | None = None) -> None:
        self.config = config or DaemonConfig()
        self._stop_event = threading.Event()
        self._running = False
        self._started_at: float | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._tick_count = 0
        self._agent_executor = AgentExecutor()
        self._last_results: list[AgentExecutionResult] = []

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop_signal)
        signal.signal(signal.SIGTERM, self._handle_stop_signal)

    def _config_path(self) -> Path:
        return _PROJECT_ROOT / self.config.config_path

    def _handle_stop_signal(self, signum: int, frame: Any) -> None:
        self.stop()

    def _increment_tick(self) -> int:
        with self._lock:
            self._tick_count += 1
            return self._tick_count

    def _load_config_manager(self) -> ConfigManager | None:
        config_path = self._config_path()
        if not config_path.exists():
            return None
        return ConfigManager(config_path=config_path)

    def _select_daemon_agents(self, manager: ConfigManager) -> list[DaemonAgent]:
        return [agent for agent in manager.get_enabled_agents() if isinstance(agent, DaemonAgent)]


    def _execute_daemon_agents(self, agents: list[DaemonAgent], tick_count: int) -> list[AgentExecutionResult]:
        return [
            self._agent_executor.execute(
                agent=agent,
                messages=[{"role": "user", "content": f"Daemon tick {tick_count}"}],
            )
            for agent in agents
        ]

    def _set_last_results(self, results: list[AgentExecutionResult]) -> None:
        with self._lock:
            self._last_results = results

    def _serialize_result(self, result: AgentExecutionResult) -> dict[str, Any]:
        return {
            "agent_name": result.agent_name,
            "success": result.success,
            "output": result.output,
        }

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._stop_event.clear()
            self._running = True
            self._started_at = time.time()
            self._thread = threading.Thread(target=self.run_loop, daemon=True)
            self._thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._running = False
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=self.config.shutdown_timeout_sec)
        return True

    def run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._run_tick()
            self._stop_event.wait(self.config.tick_interval_sec)

    def _run_tick(self) -> None:
        tick_count = self._increment_tick()
        manager = self._load_config_manager()
        if manager is None:
            self._set_last_results([])
            return
        daemon_agents = self._select_daemon_agents(manager)
        results = self._execute_daemon_agents(daemon_agents, tick_count)
        self._set_last_results(results)

    def last_results(self) -> list[AgentExecutionResult]:
        with self._lock:
            return list(self._last_results)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.config.name,
                "running": self._running,
                "pid": os.getpid(),
                "started_at": self._started_at,
                "tick_count": self._tick_count,
                "tick_interval_sec": self.config.tick_interval_sec,
                "config_path": self.config.config_path,
                "last_results": [self._serialize_result(result) for result in self._last_results],
            }
        
    def generate(self, agent, messages: list[dict[str, str]], enabled_skills: dict[str, bool],):
        self._agent_executor(
            agent=agent,
            messages=messages,
            enabled_skills=enabled_skills
        )


def create_app() -> Any:
    fastapi_module = __import__("fastapi", fromlist=["FastAPI"])
    pydantic_module = __import__("pydantic", fromlist=["BaseModel"])
    FastAPI = fastapi_module.FastAPI
    BaseModel = pydantic_module.BaseModel

    daemon = ServerDaemon()
    app = FastAPI(title="Sample Daemon API", version="0.1.0")
    app.state.daemon = daemon

    class StartResponse(BaseModel):
        started: bool
        status: dict[str, Any]

    class StopResponse(BaseModel):
        stopped: bool
        status: dict[str, Any]

    class StatusResponse(BaseModel):
        status: dict[str, Any]

    class ConfigPatchRequest(BaseModel):
        tick_interval_sec: float | None = None
        shutdown_timeout_sec: float | None = None
        name: str | None = None

    class ConfigResponse(BaseModel):
        config: dict[str, Any]

    @app.get("/daemon/config", response_model=ConfigResponse)
    def get_config() -> ConfigResponse:
        return ConfigResponse(config={
            "name": daemon.config.name,
            "tick_interval_sec": daemon.config.tick_interval_sec,
            "shutdown_timeout_sec": daemon.config.shutdown_timeout_sec,
            "config_path": daemon.config.config_path,
        })

    @app.patch("/daemon/config", response_model=ConfigResponse)
    def patch_config(req: ConfigPatchRequest) -> ConfigResponse:
        if req.tick_interval_sec is not None:
            daemon.config.tick_interval_sec = req.tick_interval_sec
        if req.shutdown_timeout_sec is not None:
            daemon.config.shutdown_timeout_sec = req.shutdown_timeout_sec
        if req.name is not None:
            daemon.config.name = req.name
        return ConfigResponse(config={
            "name": daemon.config.name,
            "tick_interval_sec": daemon.config.tick_interval_sec,
            "shutdown_timeout_sec": daemon.config.shutdown_timeout_sec,
            "config_path": daemon.config.config_path,
        })

    @app.on_event("startup")
    def on_startup() -> None:
        daemon.install_signal_handlers()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/daemon/start", response_model=StartResponse)
    def start_daemon() -> StartResponse:
        started = daemon.start()
        return StartResponse(started=started, status=daemon.status())

    @app.post("/daemon/stop", response_model=StopResponse)
    def stop_daemon() -> StopResponse:
        stopped = daemon.stop()
        return StopResponse(stopped=stopped, status=daemon.status())

    @app.get("/daemon/status", response_model=StatusResponse)
    def daemon_status() -> StatusResponse:
        return StatusResponse(status=daemon.status())

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
