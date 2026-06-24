"""Pydantic request/response schemas for the Gabriel REST + WebSocket API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
class AgentSummary(BaseModel):
    name: str
    type: str
    provider: str
    model: str
    endpoint: Optional[str] = None
    enabled: bool = True
    system_prompt: Optional[str] = None
    timeout_seconds: int = 20
    temperature: float = 0.0
    max_tokens: Optional[int] = None


class AgentCreate(BaseModel):
    name: str
    type: str
    provider: str
    model: str
    endpoint: Optional[str] = None
    system_prompt: Optional[str] = None
    timeout_seconds: int = 20
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    enabled: bool = True


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    timeout_seconds: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
class Message(BaseModel):
    role: str
    content: str


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    agent_name: Optional[str] = None
    message_count: int = 0


class SessionDetail(BaseModel):
    id: str
    title: str
    created_at: str
    agent_name: Optional[str] = None
    messages: list[Message] = Field(default_factory=list)


class SessionCreate(BaseModel):
    agent_name: Optional[str] = None
    title: Optional[str] = None


class MessageCreate(BaseModel):
    role: str = "user"
    content: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    session_id: str
    message: str
    agent_name: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    agent_name: str
    success: bool
    output: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class ToolSummary(BaseModel):
    id: str
    display_name: str
    category: str
    description: str = ""


class ToolListResponse(BaseModel):
    tools: list[ToolSummary]


class ToolToggleRequest(BaseModel):
    agent_id: str
    tool_id: str
    enabled: bool


class AgentToolStates(BaseModel):
    agent_id: str
    states: dict[str, bool]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
class MemoryChunk(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryListResponse(BaseModel):
    count: int
    grouped: dict[str, list[MemoryChunk]]


class MemoryDeleteRequest(BaseModel):
    ids: list[str]


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class OkResponse(BaseModel):
    ok: bool = True
    detail: Optional[str] = None
