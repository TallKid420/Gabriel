from __future__ import annotations

import logging

from agents.base_agent import BaseAgent
from agents.registry import AGENT_REGISTRY
from config.config_loader import AgentConfig


log = logging.getLogger(__name__)


class AgentFactory:
    _CACHE: dict[str, BaseAgent] = {}

    @staticmethod
    def _to_base_agent(config: AgentConfig) -> BaseAgent:
        data = {
            "name": config.name,
            "type": config.type,
            "provider": config.provider,
            "model": config.model,
            "enabled": config.enabled,
            "endpoint": config.endpoint,
            "timeout_seconds": config.timeout_seconds,
            "temperature": config.temperature,
            "top_p": config.extra.get("top_p", 1.0),
            "max_tokens": config.extra.get("max_tokens"),
            "context_window": config.extra.get("context_window"),
            "tools": config.tools,
            "system_prompt": config.system_prompt,
            **config.extra,
        }
        return BaseAgent.from_dict(data)

    @classmethod
    def spawn(cls, config: AgentConfig) -> BaseAgent:
        key = config.agent_id or config.name
        cached = cls._CACHE.get(key)
        if cached:
            return cached

        agent_type = str(config.type).strip().lower()
        agent_class = AGENT_REGISTRY.get(agent_type)
        if not agent_class:
            raise ValueError(
                f"Unknown agent type: '{config.type}'. "
                f"Registered types: {list(AGENT_REGISTRY.keys())}"
            )

        base_agent = cls._to_base_agent(config)
        if isinstance(base_agent, agent_class):
            agent = base_agent
        else:
            agent = agent_class(**base_agent.to_dict(), extra=base_agent.extra)
        agent.validate()
        cls._CACHE[key] = agent
        return agent

    @classmethod
    def spawn_system(cls, configs: list[AgentConfig]) -> list[BaseAgent]:
        agents: list[BaseAgent] = []
        for config in configs:
            try:
                agents.append(cls.spawn(config))
            except Exception as exc:
                log.error("Failed to spawn system agent '%s': %s", config.name, exc)
        return agents

    @classmethod
    def spawn_custom(cls, configs: list[AgentConfig]) -> list[BaseAgent]:
        agents: list[BaseAgent] = []
        for config in configs:
            try:
                agents.append(cls.spawn(config))
            except Exception as exc:
                log.error("Failed to spawn custom agent '%s': %s", config.name, exc)
        return agents
