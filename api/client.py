"""GabrielAPIClient — the thin HTTP/SSE client Streamlit uses to talk to the
FastAPI backend. Keeps all networking concerns out of the view modules.

The backend base URL is read from the ``GABRIEL_API_URL`` env var and defaults
to ``http://127.0.0.1:8000``.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator, Optional

import httpx

DEFAULT_BASE_URL = os.environ.get("GABRIEL_API_URL", "http://127.0.0.1:8000")


class GabrielAPIClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    # -- low level -----------------------------------------------------------
    def _get(self, path: str, **kwargs) -> Any:
        r = httpx.get(f"{self.base_url}{path}", timeout=self._timeout, **kwargs)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json_body: Optional[dict] = None) -> Any:
        r = httpx.post(f"{self.base_url}{path}", json=json_body, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, json_body: dict) -> Any:
        r = httpx.patch(f"{self.base_url}{path}", json=json_body, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str, json_body: Optional[dict] = None) -> Any:
        r = httpx.request(
            "DELETE", f"{self.base_url}{path}", json=json_body, timeout=self._timeout
        )
        r.raise_for_status()
        return r.json()

    # -- health --------------------------------------------------------------
    def health(self) -> bool:
        try:
            return self._get("/health").get("status") == "ok"
        except Exception:
            return False

    # -- agents --------------------------------------------------------------
    def list_agents(self, enabled_only: bool = False) -> list[dict]:
        return self._get(
            "/api/agents", params={"enabled_only": str(enabled_only).lower()}
        )["agents"]

    def create_agent(self, payload: dict) -> dict:
        return self._post("/api/agents", payload)

    def update_agent(self, name: str, payload: dict) -> dict:
        return self._patch(f"/api/agents/{name}", payload)

    def delete_agent(self, name: str) -> dict:
        return self._delete(f"/api/agents/{name}")

    def enable_agent(self, name: str) -> dict:
        return self._post(f"/api/agents/{name}/enable")

    def disable_agent(self, name: str) -> dict:
        return self._post(f"/api/agents/{name}/disable")

    # -- sessions ------------------------------------------------------------
    def list_sessions(self) -> list[dict]:
        return self._get("/api/sessions")["sessions"]

    def get_session(self, session_id: str) -> dict:
        return self._get(f"/api/sessions/{session_id}")

    def create_session(
        self, agent_name: Optional[str] = None, title: Optional[str] = None
    ) -> dict:
        return self._post("/api/sessions", {"agent_name": agent_name, "title": title})

    def delete_session(self, session_id: str) -> dict:
        return self._delete(f"/api/sessions/{session_id}")

    def clear_session(self, session_id: str) -> dict:
        return self._post(f"/api/sessions/{session_id}/clear")

    # -- chat ----------------------------------------------------------------
    def chat(self, session_id: str, message: str, agent_name: Optional[str] = None) -> dict:
        return self._post(
            "/api/chat",
            {"session_id": session_id, "message": message, "agent_name": agent_name},
        )

    def chat_stream(
        self, session_id: str, message: str, agent_name: Optional[str] = None
    ) -> Iterator[dict]:
        """Yield normalized events from the SSE streaming endpoint."""
        body = {"session_id": session_id, "message": message, "agent_name": agent_name}
        with httpx.stream(
            "POST", f"{self.base_url}/api/chat/stream", json=body, timeout=None
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    yield json.loads(line[len("data: "):])

    # -- tools ---------------------------------------------------------------
    def list_tools(self) -> list[dict]:
        return self._get("/api/tools")["tools"]

    def list_tool_agents(self) -> list[dict]:
        return self._get("/api/tools/agents")["agents"]

    def get_agent_tool_states(self, agent_id: str) -> dict[str, bool]:
        return self._get(f"/api/tools/agents/{agent_id}/states")["states"]

    def toggle_tool(self, agent_id: str, tool_id: str, enabled: bool) -> dict:
        return self._post(
            "/api/tools/toggle",
            {"agent_id": agent_id, "tool_id": tool_id, "enabled": enabled},
        )

    # -- memory --------------------------------------------------------------
    def list_memories(self) -> dict:
        return self._get("/api/memory")

    def delete_memories(self, ids: list[str]) -> dict:
        return self._delete("/api/memory", {"ids": ids})
