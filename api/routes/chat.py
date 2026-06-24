"""Chat REST endpoints (non-streaming + Server-Sent-Events streaming).

WebSocket streaming lives in ``api/websocket.py``; this module offers an HTTP
fallback (SSE) for clients that cannot hold a socket open.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.dependencies import get_agent_service, get_session_service
from api.schemas import ChatRequest, ChatResponse
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _prepare_turn(req: ChatRequest, sessions: SessionService):
    session = sessions.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    # Persist the user's message and resolve the agent for this turn.
    sessions.append_message(req.session_id, "user", req.message)
    if req.agent_name and session.agent_name != req.agent_name:
        sessions.set_agent(req.session_id, req.agent_name)
    refreshed = sessions.get_session(req.session_id)
    agent_name = req.agent_name or refreshed.agent_name
    return refreshed, agent_name


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
):
    session, agent_name = _prepare_turn(req, sessions)
    try:
        result = agents.chat(
            messages=session.messages, agent_name=agent_name, thread_id=session.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sessions.append_message(req.session_id, "assistant", result["output"])
    return ChatResponse(
        session_id=req.session_id,
        agent_name=result["agent_name"],
        success=result["success"],
        output=result["output"],
    )


@router.post("/stream")
def chat_stream(
    req: ChatRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
):
    """Stream normalized events as Server-Sent-Events (text/event-stream)."""
    session, agent_name = _prepare_turn(req, sessions)

    def event_gen():
        full_text_parts: list[str] = []
        for event in agents.stream(
            messages=session.messages, agent_name=agent_name, thread_id=session.id
        ):
            if event["type"] == "token":
                full_text_parts.append(event["content"])
            if event["type"] == "done":
                # done.content is authoritative; persist the assistant reply.
                final = event.get("content") or "".join(full_text_parts)
                sessions.append_message(req.session_id, "assistant", final)
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
