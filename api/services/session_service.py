"""
SessionService
==============

Owns chat-session domain logic and persistence. This is the single source of
truth for sessions, extracted out of the Streamlit entry point (``app.py``).

The service is intentionally free of any Streamlit imports so it can run inside
the FastAPI process (the system of record) while Streamlit talks to it over
HTTP. ``ChatSession`` is re-exported by ``app.py`` for backwards compatibility

Persistence now lives in the unified PostgreSQL database via
:class:'db.respositories.SessionRepository' (previously a '''sessions.json''' file).
"""

from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from db.repositories import SessionRepository

# Retained only so legacy ''from api.services.session_service import SESSIONS_FILE'''
# import keep resolving. Sessions are no longer stored in this file.
# TODO: Remove this from other files
SESSIONS_FILE = Path(__file__).resolve().parents[2] / "database" / "sessions.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    agent_name: Optional[str] = None
    messages: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "agent_name": self.agent_name,
            "messages": self.messages,
        }

    @staticmethod
    def from_dict(data: dict[str, object]) -> "ChatSession":
        return ChatSession(
            id=str(data.get("id", "")),
            title=str(data.get("title", "New chat")),
            created_at=str(data.get("created_at", "")),
            agent_name=data.get("agent_name"),
            messages=list(data.get("messages", [])),
        )


class SessionService:
    """CRUD + persistence for chat sessions, backed by a JSON file."""

    def __init__(self, sessions_file: Path | str | None = None) -> None:
        if sessions_file is not None:
            warnings.warn(
                "sessions_file parameter is deprecated and will be removed in a future version",
                DeprecationWarning,
                stacklevel=2,
            )
        self._repo = SessionRepository()

    # -- persistence (legacy compat shims) -----------------------------------
    def _load_raw(self) -> dict[str, ChatSession]:
        return {
            s["id"]: ChatSession.from_dict(s) for s in self._repo.list_sessions()
        }

    def _save_raw(self, sessions: dict[str, ChatSession]) -> None:
        self._repo.replace_all([s.to_dict() for s in sessions.values()])

    # -- public API ----------------------------------------------------------
    def list_sessions(self) -> list[ChatSession]:
        return [ChatSession.from_dict(s) for s in self._repo.list_sessions()]

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        data = self._repo.get_session(session_id)
        return ChatSession.from_dict(data) if data is not None else None

    def create_session(
        self, agent_name: Optional[str] = None, title: Optional[str] = None
    ) -> ChatSession:
        session_id = str(uuid.uuid4())
        session = ChatSession(
            id=session_id,
            title=title or (f"{agent_name} chat" if agent_name else "New chat"),
            created_at=now_iso(),
            agent_name=agent_name,
            messages=[],
        )
        self._repo.create_session(
            session.id, session.title, session.created_at, session.agent_name
        )
        return session

    def delete_session(self, session_id: str) -> bool:
        return self._repo.delete_session(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        if not self._repo.exists(session_id):
            raise KeyError(f"Session '{session_id}' not found")
        self._repo.append_message(session_id, role, content)

        # Re-derive the auto-title from the (now updated) message list.
        session = self.get_session(session_id)
        previous_title = session.title
        self._maybe_update_title(session)
        if session.title != previous_title:
            self._repo.update_title(session_id, session.title)
        return self.get_session(session_id)

    def set_agent(self, session_id: str, agent_name: str) -> ChatSession:
        if not self._repo.set_agent(session_id, agent_name):
            raise KeyError(f"Session '{session_id}' not found")
        return self.get_session(session_id)

    def clear_messages(self, session_id: str) -> ChatSession:
        if not self._repo.clear_messages(session_id):
            raise KeyError(f"Session '{session_id}' not found")
        return self.get_session(session_id)

    @staticmethod
    def _maybe_update_title(session: ChatSession) -> None:
        if session.title == "New chat":
            user_messages = [
                m["content"] for m in session.messages if m["role"] == "user"
            ]
            if user_messages:
                session.title = user_messages[0][:48] or "New chat"
