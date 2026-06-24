"""WebSocket chat streaming endpoint: ``/ws/chat``.

Protocol
--------
Client -> server (first frame, JSON):
    {"session_id": "<id>", "message": "<text>", "agent_name": "<optional>"}

Server -> client (many frames, JSON), the normalized event contract produced by
``AgentService.stream``:
    {"type": "status",      "status": "started", "agent": "<name>"}
    {"type": "token",       "content": "<delta>"}
    {"type": "tool_start",  "name": "<tool>", "input": {...}}
    {"type": "tool_output", "name": "<tool>", "content": "<text>"}
    {"type": "tool_end",    "name": "<tool>", "output": "<text>"}
    {"type": "error",       "message": "<text>"}
    {"type": "done",        "content": "<full assistant text>"}

The agent stream is a *synchronous* generator (langgraph), so it is pumped on a
worker thread and bridged to the event loop via an ``asyncio.Queue`` to avoid
blocking other sockets.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.dependencies import get_agent_service, get_session_service

router = APIRouter(tags=["websocket"])

_SENTINEL = object()


@router.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    agents=Depends(get_agent_service),
    sessions=Depends(get_session_service),
) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            session_id = payload.get("session_id")
            message = payload.get("message", "")
            agent_name = payload.get("agent_name")

            session = sessions.get_session(session_id)
            if session is None:
                await websocket.send_json(
                    {"type": "error", "message": "Session not found"}
                )
                continue

            sessions.append_message(session_id, "user", message)
            if agent_name and session.agent_name != agent_name:
                sessions.set_agent(session_id, agent_name)
            session = sessions.get_session(session_id)
            resolved_agent = agent_name or session.agent_name

            await _pump_stream(websocket, agents, sessions, session, resolved_agent)
    except WebSocketDisconnect:
        return


async def _pump_stream(websocket, agents, sessions, session, agent_name) -> None:
    """Run the sync agent stream on a thread; relay events to the socket."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    final_text_parts: list[str] = []

    def producer() -> None:
        try:
            for event in agents.stream(
                messages=session.messages,
                agent_name=agent_name,
                thread_id=session.id,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # pragma: no cover - defensive
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(exc)}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    task = loop.run_in_executor(None, producer)
    try:
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            if event.get("type") == "token":
                final_text_parts.append(event.get("content", ""))
            if event.get("type") == "done":
                final = event.get("content") or "".join(final_text_parts)
                sessions.append_message(session.id, "assistant", final)
            await websocket.send_json(event)
    finally:
        await task
