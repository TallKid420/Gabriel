from __future__ import annotations

import queue
import threading
from typing import Any, Iterator, Optional

from api.services.config_service import ConfigService
from security.permission_tool import set_event_callback


class AgentService:
    def __init__(self, config_service: Optional[ConfigService] = None) -> None:
        self._config = config_service or ConfigService()
        self._executor = None

    @property
    def executor(self):
        if self._executor is None:
            from agents.executor import AgentExecutor
            self._executor = AgentExecutor()
        return self._executor

    def chat(self, messages, agent_name, thread_id) -> dict[str, Any]:
        agent = self._config.resolve_chat_agent(agent_name)
        if agent is None:
            raise ValueError("No enabled agents available for chat")
        result = self.executor.execute(agent=agent, messages=messages, thread_id=thread_id)
        return {"agent_name": result.agent_name, "success": result.success, "output": result.output}

    def stream(self, messages, agent_name, thread_id) -> Iterator[dict[str, Any]]:
        agent = self._config.resolve_chat_agent(agent_name)
        if agent is None:
            yield {"type": "error", "message": "No enabled agents available for chat"}
            return

        yield {"type": "status", "status": "started", "agent": agent.name}

        # Thread-safe queue so the tool thread can inject permission_request
        # events into this generator's output.
        event_queue: queue.SimpleQueue = queue.SimpleQueue()
        _DONE = object()

        def _cb(event: dict) -> None:
            event_queue.put(event)

        set_event_callback(_cb)

        full_text_parts: list[str] = []
        error_holder: list[str] = []

        def _run_stream():
            try:
                raw_stream = self.executor.execute_stream(
                    agent=agent, messages=messages, thread_id=thread_id
                )
                for chunk in raw_stream:
                    for event in self._normalize_chunk(chunk):
                        event_queue.put(event)
            except Exception as exc:
                error_holder.append(str(exc))
            finally:
                event_queue.put(_DONE)

        t = threading.Thread(target=_run_stream, daemon=True)
        t.start()

        while True:
            item = event_queue.get()
            if item is _DONE:
                break
            if item.get("type") == "token":
                full_text_parts.append(item.get("content", ""))
            yield item

        t.join()
        set_event_callback(None)

        if error_holder:
            yield {"type": "error", "message": error_holder[0]}
            return

        yield {"type": "done", "content": "".join(full_text_parts)}

    # ── normalization (unchanged from original) ──────────────────────────────

    def _normalize_chunk(self, chunk: Any) -> list[dict[str, Any]]:
        if isinstance(chunk, str):
            return [{"type": "token", "content": chunk}] if chunk else []
        if not isinstance(chunk, dict):
            return []
        ctype = chunk.get("type")
        if ctype == "messages":
            return self._tokens_from_messages(chunk.get("data"))
        if ctype == "text":
            text = chunk.get("content", "")
            return [{"type": "token", "content": text}] if text else []
        if ctype == "tool_start":
            return [{"type": "tool_start", "name": chunk.get("name", "unknown"), "input": chunk.get("input", {})}]
        if ctype == "tool_output":
            return [{"type": "tool_output", "name": chunk.get("name", "unknown"), "content": str(chunk.get("content", ""))}]
        if ctype == "tool_end":
            raw_output = chunk.get("output")
            output = "" if raw_output is None else (getattr(raw_output, "content", None) or str(raw_output))
            return [{"type": "tool_end", "name": chunk.get("name", "unknown"), "output": output}]
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
                text = "".join(t.get("text", "") if isinstance(t, dict) else str(t) for t in text)
            return [{"type": "token", "content": text}] if text else []
        if event == "on_tool_start":
            return [{"type": "tool_start", "name": name, "input": data.get("input", {})}]
        if event == "on_tool_end":
            output = data.get("output")
            output = getattr(output, "content", None) or str(output or "")
            return [{"type": "tool_end", "name": name, "output": output}]
        return []