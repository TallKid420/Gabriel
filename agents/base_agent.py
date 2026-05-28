from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID


AGENT_TYPE_MAP: dict[str, str] = {
    "chat": "ChatAgent",
    "engineer": "EngineerAgent",
    "researcher": "ResearcherAgent",
    "server": "ServerAgent",
    "daemon": "DaemonAgent",
}

@dataclass
class BaseAgent:
    name: str
    type: str
    provider: str
    model: str

    enabled: bool = True
    endpoint: Optional[str] = None
    timeout_seconds: int = 20
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    context_window: Optional[int] = None

    # Flexible fields
    tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None

    agent_id: UUID | str = None
    # Extra metadata storage
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseAgent":
        known_fields = {
            "name",
            "type",
            "provider",
            "model",
            "enabled",
            "endpoint",
            "timeout_seconds",
            "temperature",
            "top_p",
            "max_tokens",
            "context_window",
            "tools",
            "system_prompt",
            "agent_id",
        }

        extracted = {k: v for k, v in data.items() if k in known_fields}
        extra = {k: v for k, v in data.items() if k not in known_fields}
        agent_type = str(extracted.get("type", "")).strip().lower()

        if cls is BaseAgent and agent_type in AGENT_TYPE_MAP:
            if agent_type == "chat":
                from agents.types.chat_agent import ChatAgent

                return ChatAgent(**extracted, extra=extra)
            if agent_type == "engineer":
                from agents.types.engineer_agent import EngineerAgent

                return EngineerAgent(**extracted, extra=extra)
            if agent_type == "researcher":
                from agents.types.researcher_agent import ResearcherAgent

                return ResearcherAgent(**extracted, extra=extra)
            if agent_type == "server":
                from agents.server_agent import ServerAgent

                return ServerAgent(**extracted, extra=extra)
            if agent_type == "daemon":
                from agents.types.daemon_agent import DaemonAgent

                return DaemonAgent(**extracted, extra=extra)

        return cls(**extracted, extra=extra)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)

        extra = data.pop("extra", {})
        data.update(extra)

        return {k: v for k, v in data.items() if v is not None}

    def validate(self) -> None:
        if not self.name:
            raise ValueError("Agent name is required")
        if not self.type:
            raise ValueError("Agent type is required")
        if not self.provider:
            raise ValueError("Agent provider is required")
        if not self.model:
            raise ValueError("Agent model is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        if not (0.0 <= self.top_p <= 1.0):
            raise ValueError("top_p must be between 0.0 and 1.0")

    def get_tools(self) -> List[Any]:
        return []

    def run_stream(self, user_input: str):
        yield str(getattr(self, "run")(user_input))