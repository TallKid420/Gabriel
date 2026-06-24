"""
ConfigService
=============

Owns agent configuration (the ``config/agents.yaml`` catalog) via the existing
``ConfigManager``. Provides read + CRUD operations for agents so that neither
Streamlit nor the route handlers touch ``ConfigManager`` directly.

The ``ConfigManager`` import is performed lazily because its import chain pulls
in langchain/langgraph; keeping it lazy lets the FastAPI app import cleanly in
environments where the heavy ML stack is not installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

CONFIG_PATH = str(Path(__file__).resolve().parents[2] / "config" / "agents.yaml")


class ConfigService:
    def __init__(self, config_path: str = CONFIG_PATH) -> None:
        self._config_path = config_path
        self._manager = None  # lazy

    @property
    def manager(self):
        if self._manager is None:
            from config.config_manager import ConfigManager

            self._manager = ConfigManager(self._config_path)
        return self._manager

    def reload(self) -> None:
        self.manager.load()

    # -- reads ---------------------------------------------------------------
    def list_agents(self) -> list[Any]:
        return self.manager.system_agents + self.manager.custom_agents

    def list_enabled_agents(self) -> list[Any]:
        return self.manager.get_enabled_agents()

    def get_agent(self, name: str):
        return self.manager.get_agent(name)

    def get_agents_by_type(self, agent_type: str) -> list[Any]:
        return self.manager.get_agents_by_type(agent_type)

    # -- writes --------------------------------------------------------------
    def add_agent(self, agent_data: dict[str, Any], section: str = "custom_agents"):
        return self.manager.add_agent(agent_data, section=section)

    def update_agent(self, current_name: str, agent_data: dict[str, Any]) -> bool:
        return self.manager.update_agent(current_name, agent_data)

    def remove_agent(self, name: str) -> bool:
        return self.manager.remove_agent(name)

    def enable_agent(self, name: str) -> bool:
        return self.manager.enable_agent(name)

    def disable_agent(self, name: str) -> bool:
        return self.manager.disable_agent(name)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def agent_to_summary(agent) -> dict[str, Any]:
        return {
            "name": agent.name,
            "type": agent.type,
            "provider": agent.provider,
            "model": agent.model,
            "endpoint": agent.endpoint,
            "enabled": bool(agent.enabled),
            "system_prompt": agent.system_prompt,
            "timeout_seconds": agent.timeout_seconds,
            "temperature": float(agent.temperature),
            "max_tokens": agent.max_tokens,
        }

    def resolve_chat_agent(self, preferred_name: Optional[str] = None):
        """Pick an agent for a chat turn: preferred name -> chat-type -> any."""
        enabled = self.list_enabled_agents()
        if not enabled:
            return None
        if preferred_name:
            match = next((a for a in enabled if a.name == preferred_name), None)
            if match:
                return match
        chat_agents = [a for a in enabled if a.type == "chat"]
        return chat_agents[0] if chat_agents else enabled[0]
