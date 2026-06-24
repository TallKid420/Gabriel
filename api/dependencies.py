"""Process-wide service singletons + FastAPI dependency providers.

Services are instantiated lazily (their heavy ML imports only fire on first
use), so importing this module — and therefore the FastAPI app — is cheap and
safe even where langchain/chroma are not installed.
"""

from __future__ import annotations

from functools import lru_cache

from api.services.agent_service import AgentService
from api.services.config_service import ConfigService
from api.services.memory_service import MemoryService
from api.services.session_service import SessionService
from api.services.tool_service import ToolService


@lru_cache(maxsize=1)
def get_config_service() -> ConfigService:
    return ConfigService()


@lru_cache(maxsize=1)
def get_session_service() -> SessionService:
    return SessionService()


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return AgentService(config_service=get_config_service())


@lru_cache(maxsize=1)
def get_tool_service() -> ToolService:
    return ToolService()


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    return MemoryService()
