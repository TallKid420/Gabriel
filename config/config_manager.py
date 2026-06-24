# config_manager.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agents.base_agent import BaseAgent
from agents.factory import AgentFactory
from config.config_loader import load, load_custom_agents, load_system_agents


# =========================
# Config Manager
# =========================

class ConfigManager:
    def __init__(self, config_path: Optional[str | Path] = "agents.yaml"):
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )

        self.raw_config: Dict[str, Any] = {}
        self.system_agents: List[BaseAgent] = []
        self.custom_agents: List[BaseAgent] = []

        self.load()

    # =========================
    # Loading / Saving
    # =========================

    def load(self) -> None:
        self.raw_config = load(self.config_path)

        self.system_agents = AgentFactory.spawn_system(load_system_agents(self.config_path))
        self.custom_agents = AgentFactory.spawn_custom(load_custom_agents(self.config_path))

        for agent in self.system_agents + self.custom_agents:
            agent.validate()

    def save(self) -> None:
        config = {
            "system_agents": {
                "agents": [
                    agent.to_dict()
                    for agent in self.system_agents
                ]
            },
            "custom_agents": {
                "agents": [
                    agent.to_dict()
                    for agent in self.custom_agents
                ]
            },
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                config,
                f,
                sort_keys=False,
                default_flow_style=False
            )

    # =========================
    # Agent Retrieval
    # =========================

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        all_agents = self.system_agents + self.custom_agents

        for agent in all_agents:
            if agent.name == name:
                return agent

        return None

    def get_enabled_agents(self) -> List[BaseAgent]:
        return [
            agent
            for agent in (self.system_agents + self.custom_agents)
            if agent.enabled
        ]

    def get_agents_by_type(self, agent_type: str) -> List[BaseAgent]:
        return [
            agent
            for agent in (self.system_agents + self.custom_agents)
            if agent.type == agent_type
        ]

    # =========================
    # Agent Management
    # =========================

    def add_agent(
        self,
        agent_data: Dict[str, Any],
        section: str = "custom_agents"
    ) -> BaseAgent:

        agent = BaseAgent.from_dict(agent_data)
        agent.validate()

        if self.get_agent(agent.name):
            raise ValueError(
                f"Agent '{agent.name}' already exists"
            )

        if section == "system_agents":
            self.system_agents.append(agent)

        elif section == "custom_agents":
            self.custom_agents.append(agent)

        else:
            raise ValueError(
                "Section must be 'system_agents' or 'custom_agents'"
            )

        self.save()

        return agent

    def remove_agent(self, name: str) -> bool:
        for group in [self.system_agents, self.custom_agents]:
            for agent in group:
                if agent.name == name:
                    group.remove(agent)
                    self.save()
                    return True

        return False

    def update_agent(self, current_name: str, agent_data: Dict[str, Any]) -> bool:
        """Update an existing agent with new data."""
        agent = self.get_agent(current_name)
        
        if not agent:
            return False
        
        # Check if new name conflicts with another agent
        new_name = agent_data.get("name")
        if new_name and new_name != current_name and self.get_agent(new_name):
            raise ValueError(f"Agent '{new_name}' already exists")
        
        # Update agent fields
        for key, value in agent_data.items():
            if key in ["name", "endpoint", "model", "system_prompt", "timeout_seconds", "temperature", "max_tokens"]:
                if value is not None:
                    setattr(agent, key, value)
        
        agent.validate()
        self.save()
        return True

    def enable_agent(self, name: str) -> bool:
        agent = self.get_agent(name)

        if not agent:
            return False

        agent.enabled = True
        self.save()

        return True

    def disable_agent(self, name: str) -> bool:
        agent = self.get_agent(name)

        if not agent:
            return False

        agent.enabled = False
        self.save()

        return True

    # =========================
    # Spawn Helpers
    # =========================

    def build_runtime_config(self, name: str) -> Dict[str, Any]:
        agent = self.get_agent(name)

        if not agent:
            raise ValueError(
                f"Agent '{name}' not found"
            )

        if not agent.enabled:
            raise ValueError(
                f"Agent '{name}' is disabled"
            )

        return {
            "name": agent.name,
            "type": agent.type,
            "provider": agent.provider,
            "model": agent.model,
            "endpoint": agent.endpoint,
            "timeout_seconds": agent.timeout_seconds,
            "temperature": agent.temperature,
            "top_p": agent.top_p,
            "max_tokens": agent.max_tokens,
            "context_window": agent.context_window,
            "system_prompt": agent.system_prompt,
            **agent.extra,
        }
