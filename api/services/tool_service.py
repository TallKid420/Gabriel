"""
ToolService
===========

Owns tool discovery (the file-system registry) and per-agent tool enablement
(the SQLite ``agent_tools`` table). Extracted out of ``views/tools.py`` so the
UI no longer touches ``load_tool_registry`` or ``Database`` directly.

Heavy imports (``executor.toolhandler`` pulls langchain tools, ``daemon.database``
pulls langchain/chroma) are performed lazily.
"""

from __future__ import annotations

from typing import Any, Optional


class ToolService:
    def __init__(self) -> None:
        self._registry = None
        self._db = None

    @property
    def registry(self):
        if self._registry is None:
            from executor.toolhandler import load_tool_registry

            self._registry = load_tool_registry()
        return self._registry

    @property
    def db(self):
        if self._db is None:
            from daemon.database import Database

            self._db = Database()
        return self._db

    # -- discovery -----------------------------------------------------------
    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "id": rec.id,
                "display_name": rec.display_name,
                "category": rec.category,
                "description": rec.description,
            }
            for rec in self.registry.list_tools()
        ]

    def list_categories(self) -> list[str]:
        return sorted({rec.category for rec in self.registry.list_tools()})

    # -- per-agent enablement ------------------------------------------------
    def sync_agent_tools(self, agent_id: str) -> None:
        tool_ids = [rec.id for rec in self.registry.list_tools()]
        self.db.sync_agent_tools(agent_id, tool_ids)

    def get_agent_tool_states(self, agent_id: str) -> dict[str, bool]:
        return self.db.get_agent_tool_states(agent_id)

    def set_tool_enabled(self, agent_id: str, tool_id: str, enabled: bool) -> None:
        self.db.set_agent_tool_enabled(agent_id=agent_id, tool_id=tool_id, enabled=enabled)

    def list_agents(self) -> list[dict[str, str]]:
        return self.db.get_agents()

    def sync_agents(self, agents: list[tuple]) -> None:
        self.db.sync_agents(agents)

    # -- direct execution (optional, for a future tools endpoint) -----------
    def execute(self, tool_id: str, tool_input: Optional[dict] = None) -> Any:
        record = self.registry.get(tool_id)
        if record is None:
            raise KeyError(f"Tool '{tool_id}' not found")
        return record.callable.invoke(tool_input or {})
