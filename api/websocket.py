"""WebSocket chat streaming endpoint: ``/ws/chat``.

Protocol
--------
Client -> server (first frame, JSON):
    {"session_id": "<​id>", "message": "<​text>", "agent_name": "<​optional>"}

Server -> client (many frames, JSON):
    {"type": "status",            "status": "started", "agent": "<​name>"}
    {"type": "token",             "content": "<​delta>"}
    {"type": "tool_start",        "name": "<​tool>", "input": {...}}
    {"type": "tool_output",       "name": "<​tool>", "content": "<​text>"}
    {"type": "tool_end",          "name": "<​tool>", "output": "<​text>"}
    {"type": "permission_request","tool": "<​name>", "category": "<​cat>",
                                  "arguments": {...}}
    {"type": "error",             "message": "<​text>"}
    {"type": "done",              "content": "<​full assistant text>"}

Client -> server (permission response frame, JSON):
    {"type": "permission_response", "approved": true | false}
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from langgraph.types import Command

from api.dependencies import get_agent_service, get_session_service

log = logging.getLogger(__name__)
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

            if payload.get("type") == "permission_response":
                continue

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
    """
    Run the sync agent stream on a thread; relay events to the socket.

    When a ``permission_request`` interrupt arrives the graph is paused.
    We forward the request to the frontend and wait for a
    ``permission_response`` frame before resuming the graph.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    final_text_parts: list[str] = []

    resume_event: asyncio.Event = asyncio.Event()
    resume_value: list = [None]

    def producer(command: Command | None = None) -> None:
        try:
            stream_kwargs = dict(
                messages=session.messages,
                agent_name=agent_name,
                thread_id=session.id,
            )
            if command is not None:
                stream_kwargs["resume_command"] = command

            for event in agents.stream(**stream_kwargs):
                if event.get("type") == "permission_request":
                    loop.call_soon_threadsafe(queue.put_nowait, event)
                    loop.call_soon_threadsafe(resume_event.clear)

                    import threading
                    _thread_event = threading.Event()

                    def _set_thread_event():
                        _thread_event.set()

                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "_await_permission", "_notify": _set_thread_event},
                    )
                    _thread_event.wait()

                    return resume_value[0]
                
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

            # Internal handshake: wait for user permission response
            if isinstance(event, dict) and event.get("type") == "_await_permission":
                notify_fn = event["_notify"]
                # Wait for the frontend to send a permission_response frame
                try:
                    response_payload = await asyncio.wait_for(
                        websocket.receive_json(), timeout=120.0
                    )
                except asyncio.TimeoutError:
                    # Treat timeout as denial
                    response_payload = {"type": "permission_response", "approved": False}

                approved: bool = bool(response_payload.get("approved", False))
                resume_value[0] = approved

                # Tell the producer thread it can continue
                loop.call_soon_threadsafe(notify_fn)

                # Resume the graph with the user's decision
                resume_command = Command(resume=approved)
                await task   # wait for current producer to finish
                task = loop.run_in_executor(None, producer, resume_command)
                continue

            if event.get("type") == "token":
                final_text_parts.append(event.get("content", ""))
            if event.get("type") == "done":
                final = event.get("content") or "".join(final_text_parts)
                sessions.append_message(session.id, "assistant", final)

            await websocket.send_json(event)
    finally:
        await task