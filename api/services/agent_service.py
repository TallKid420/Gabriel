"""
AgentService
============

The orchestration boundary. Wraps the existing ``AgentExecutor`` (agent logic is
NOT rewritten) and exposes:

* ``chat``        - run a turn and return the full reply (non-streaming)
* ``stream``      - yield a sequence of **normalized** events

The key extraction here is the *stream normalizer*: previously ``views/chat.py``
parsed raw runtime chunks directly inside Streamlit widgets. That parsing now
lives here, producing a stable event contract consumed identically by the REST
layer, the WebSocket layer and the Streamlit thin client:

    {"type": "status",      "status": "started", "agent": "<name>"}
    {"type": "token",       "content": "<text delta>"}
    {"type": "tool_start",  "name": "<tool>", "input": {...}}
    {"type": "tool_output", "name": "<tool>", "content": "<text>"}
    {"type": "tool_end",    "name": "<tool>", "output": "<text>"}
    {"type": "error",       "message": "<text>"}
    {"type": "done",        "content": "<full assistant text>"}
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from api.services.config_service import ConfigService


class AgentService:
    def __init__(self, config_service: Optional[ConfigService] = None) -> None:
        self._config = config_service or ConfigService()
        self._executor = None  # lazy

    @property
    def executor(self):
        if self._executor is None:
            from agents.executor import AgentExecutor

            self._executor = AgentExecutor()
        return self._executor

    # -- non-streaming -------------------------------------------------------
    def chat(
        self, messages: list[dict[str, str]], agent_name: Optional[str], thread_id: str
    ) -> dict[str, Any]:
        agent = self._config.resolve_chat_agent(agent_name)
        if agent is None:
            raise ValueError("No enabled agents available for chat")
        result = self.executor.execute(agent=agent, messages=messages, thread_id=thread_id)
        return {
            "agent_name": result.agent_name,
            "success": result.success,
            "output": result.output,
        }

    # -- streaming -----------------------------------------------------------
    def stream(
        self, messages: list[dict[str, str]], agent_name: Optional[str], thread_id: str
    ) -> Iterator[dict[str, Any]]:
        """Yield normalized events for a chat turn."""
        agent = self._config.resolve_chat_agent(agent_name)
        if agent is None:
            yield {"type": "error", "message": "No enabled agents available for chat"}
            return

        yield {"type": "status", "status": "started", "agent": agent.name}

        full_text_parts: list[str] = []
        try:
            raw_stream = self.executor.execute_stream(
                agent=agent, messages=messages, thread_id=thread_id
            )
            for chunk in raw_stream:
                for event in self._normalize_chunk(chunk):
                    if event["type"] == "token":
                        full_text_parts.append(event["content"])
                    yield event
        except Exception as exc:  # surface runtime/agent errors as events
            yield {"type": "error", "message": str(exc)}
            return

        yield {"type": "done", "content": "".join(full_text_parts)}

    # -- normalization -------------------------------------------------------
    def _normalize_chunk(self, chunk: Any) -> list[dict[str, Any]]:
        """Convert a raw runtime chunk into zero or more normalized events.

        Handles three shapes seen across runtimes:
        1. Already-normalized dicts carrying an explicit ``type``.
        2. LangChain ``astream_events``-style dicts (``event``/``data``/``name``).
        3. Plain strings (e.g. simple ``ServerAgent`` token stream).
        """
        # Shape 3: raw string token
        if isinstance(chunk, str):
            return [{"type": "token", "content": chunk}] if chunk else []

        if not isinstance(chunk, dict):
            return []

        # Shape 1: explicit type contract used by the langgraph chat agent
        ctype = chunk.get("type")
        if ctype == "messages":
            return self._tokens_from_messages(chunk.get("data"))
        if ctype == "text":
            text = chunk.get("content", "")
            return [{"type": "token", "content": text}] if text else []
        if ctype == "tool_start":
            return [{
                "type": "tool_start",
                "name": chunk.get("name", "unknown"),
                "input": chunk.get("input", {}),
            }]
        if ctype == "tool_output":
            return [{
                "type": "tool_output",
                "name": chunk.get("name", "unknown"),
                "content": str(chunk.get("content", "")),
            }]
        if ctype == "tool_end":
            raw_output = chunk.get("output")
            output = ""
            if raw_output is not None:
                output = getattr(raw_output, "content", None) or str(raw_output)
            return [{
                "type": "tool_end",
                "name": chunk.get("name", "unknown"),
                "output": output,
            }]

        # Shape 2: LangChain astream_events fallback
        event = chunk.get("event")
        if event:
            return self._normalize_langchain_event(chunk, event)

        return []

    @staticmethod
    def _tokens_from_messages(data: Any) -> list[dict[str, Any]]:
        if not data:
            return []
        try:
            token, _metadata = data
        except (TypeError, ValueError):
            token = data
        content = getattr(token, "content", token)
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list) and content:
            first = content[0]
            text = first.get("text", "") if isinstance(first, dict) else str(first)
        return [{"type": "token", "content": text}] if text else []

    @staticmethod
    def _normalize_langchain_event(chunk: dict, event: str) -> list[dict[str, Any]]:
        data = chunk.get("data", {}) or {}
        name = chunk.get("name", "unknown")
        if event == "on_chat_model_stream":
            token = data.get("chunk")
            text = getattr(token, "content", "") if token is not None else ""
            if isinstance(text, list):
                text = "".join(
                    t.get("text", "") if isinstance(t, dict) else str(t) for t in text
                )
            return [{"type": "token", "content": text}] if text else []
        if event == "on_tool_start":
            return [{"type": "tool_start", "name": name, "input": data.get("input", {})}]
        if event == "on_tool_end":
            output = data.get("output")
            output = getattr(output, "content", None) or str(output or "")
            return [{"type": "tool_end", "name": name, "output": output}]
        return []
