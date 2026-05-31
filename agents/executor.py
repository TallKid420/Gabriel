from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import BaseAgent
from agents.factory import AgentFactory
from agents.types.chat_agent import ChatAgent
from agents.types.daemon_agent import DaemonAgent
from agents.types.engineer_agent import EngineerAgent
from agents.types.researcher_agent import ResearcherAgent
from agents.server_agent import ServerAgent
from config.config_loader import AgentConfig


@dataclass
class AgentExecutionResult:
    agent_name: str
    success: bool
    output: str


class AgentExecutor:
    TYPE_CONTRACTS: tuple[tuple[type[BaseAgent], str], ...] = (
        (ChatAgent, "chat"),
        (EngineerAgent, "engineer"),
        (ResearcherAgent, "researcher"),
        (ServerAgent, "server"),
        (DaemonAgent, "daemon"),
    )

    def __init__(self) -> None:
        pass

    def _build_enabled_skills(self, agent: BaseAgent) -> dict[str, bool]:
        configured_tools = set(agent.tools)
        discovered_tools = {tool.name for tool in agent.get_tools() if getattr(tool, "name", None)}
        return {tool_name: True for tool_name in configured_tools | discovered_tools}

    def _expected_type_for(self, agent: BaseAgent) -> str | None:
        for agent_class, expected_type in self.TYPE_CONTRACTS:
            if isinstance(agent, agent_class):
                return expected_type
        return None

    def _validate_type_contract(self, agent: BaseAgent) -> None:
        expected_type = self._expected_type_for(agent)
        if expected_type and agent.type != expected_type:
            raise ValueError(f"{agent.__class__.__name__} must have type '{expected_type}'")

    def _result(self, agent_name: str, output: str) -> AgentExecutionResult:
        return AgentExecutionResult(
            agent_name=agent_name,
            success=not str(output).startswith("Backend error:"),
            output=output,
        )

    def _to_agent_config(self, agent: BaseAgent) -> AgentConfig:
        return AgentConfig(
            name=agent.name,
            type=agent.type,
            provider=agent.provider,
            endpoint=agent.endpoint,
            timeout_seconds=agent.timeout_seconds,
            temperature=float(agent.temperature),
            model=agent.model,
            system_prompt=agent.system_prompt or "",
            tools=list(agent.tools),
            enabled=bool(agent.enabled),
            extra={
                "top_p": float(agent.top_p),
                "max_tokens": agent.max_tokens,
                "context_window": agent.context_window,
                "enabled_skills": self._build_enabled_skills(agent),
            },
        )

    def _extract_latest_user_input(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", ""))
        if not messages:
            return ""
        return str(messages[-1].get("content", ""))

    def execute(self, agent: BaseAgent, messages: list[dict[str, str]], thread_id: str) -> AgentExecutionResult:
        if not agent.enabled:
            return AgentExecutionResult(agent_name=agent.name, success=False, output=f"Agent '{agent.name}' is disabled")
        self._validate_type_contract(agent)
        agent.validate()
        runtime_agent = AgentFactory.spawn(self._to_agent_config(agent))
        output = runtime_agent.run(self._extract_latest_user_input(messages), thread_id=thread_id)
        return self._result(runtime_agent.name, output)

    def execute_stream(self, agent: BaseAgent, messages: list[dict[str, str]], thread_id: str):
        if not agent.enabled:
            yield f"Agent '{agent.name}' is disabled"
            return
        self._validate_type_contract(agent)
        agent.validate()
        runtime_agent = AgentFactory.spawn(self._to_agent_config(agent))
        user_input = self._extract_latest_user_input(messages)

        stream_fn = getattr(runtime_agent, "run_stream", None)
        
        if callable(stream_fn):
            for chunk in stream_fn(user_input, thread_id):
                yield chunk
            return
