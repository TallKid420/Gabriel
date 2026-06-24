"""Chat session REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_session_service
from api.schemas import (
    MessageCreate,
    OkResponse,
    SessionCreate,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
)
from api.services.session_service import ChatSession, SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_summary(s: ChatSession) -> SessionSummary:
    return SessionSummary(
        id=s.id,
        title=s.title,
        created_at=s.created_at,
        agent_name=s.agent_name,
        message_count=len(s.messages),
    )


def _to_detail(s: ChatSession) -> SessionDetail:
    return SessionDetail(
        id=s.id,
        title=s.title,
        created_at=s.created_at,
        agent_name=s.agent_name,
        messages=s.messages,
    )


@router.get("", response_model=SessionListResponse)
def list_sessions(svc: SessionService = Depends(get_session_service)):
    return SessionListResponse(sessions=[_to_summary(s) for s in svc.list_sessions()])


@router.post("", response_model=SessionDetail, status_code=201)
def create_session(
    payload: SessionCreate, svc: SessionService = Depends(get_session_service)
):
    session = svc.create_session(agent_name=payload.agent_name, title=payload.title)
    return _to_detail(session)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, svc: SessionService = Depends(get_session_service)):
    session = svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_detail(session)


@router.delete("/{session_id}", response_model=OkResponse)
def delete_session(session_id: str, svc: SessionService = Depends(get_session_service)):
    if not svc.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return OkResponse(detail="deleted")


@router.post("/{session_id}/messages", response_model=SessionDetail)
def append_message(
    session_id: str,
    payload: MessageCreate,
    svc: SessionService = Depends(get_session_service),
):
    try:
        session = svc.append_message(session_id, payload.role, payload.content)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_detail(session)


@router.post("/{session_id}/clear", response_model=SessionDetail)
def clear_session(session_id: str, svc: SessionService = Depends(get_session_service)):
    try:
        session = svc.clear_messages(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_detail(session)
