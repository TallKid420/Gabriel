"""
SessionService
==============

Owns chat-session domain logic and persistence. This is the single source of
truth for sessions, extracted out of the Streamlit entry point (``app.py``).

The service is intentionally free of any Streamlit imports so it can run inside
the FastAPI process (the system of record) while Streamlit talks to it over
HTTP. ``ChatSession`` is re-exported by ``app.py`` for backwards compatibility
during the migration.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Persist to the same file the legacy Streamlit app used so existing data and a
# running Streamlit instance stay compatible during the migration.
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

    def __init__(self, sessions_file: Path | str = SESSIONS_FILE) -> None:
        self._file = Path(sessions_file)
        self._lock = threading.RLock()

    # -- persistence ---------------------------------------------------------
    def _load_raw(self) -> dict[str, ChatSession]:
        if not self._file.exists():
            return {}
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return {
                sid: ChatSession.from_dict(sdata) for sid, sdata in data.items()
            }
        except Exception:
            return {}

    def _save_raw(self, sessions: dict[str, ChatSession]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: s.to_dict() for sid, s in sessions.items()}
        self._file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # -- public API ----------------------------------------------------------
    def list_sessions(self) -> list[ChatSession]:
        with self._lock:
            return list(self._load_raw().values())

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._lock:
            return self._load_raw().get(session_id)

    def create_session(
        self, agent_name: Optional[str] = None, title: Optional[str] = None
    ) -> ChatSession:
        with self._lock:
            sessions = self._load_raw()
            session_id = str(uuid.uuid4())
            session = ChatSession(
                id=session_id,
                title=title or (f"{agent_name} chat" if agent_name else "New chat"),
                created_at=now_iso(),
                agent_name=agent_name,
                messages=[],
            )
            sessions[session_id] = session
            self._save_raw(sessions)
            return session

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            sessions = self._load_raw()
            if session_id not in sessions:
                return False
            del sessions[session_id]
            self._save_raw(sessions)
            return True

    def append_message(self, session_id: str, role: str, content: str) -> ChatSession:
        with self._lock:
            sessions = self._load_raw()
            session = sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            session.messages.append({"role": role, "content": content})
            self._maybe_update_title(session)
            sessions[session_id] = session
            self._save_raw(sessions)
            return session

    def set_agent(self, session_id: str, agent_name: str) -> ChatSession:
        with self._lock:
            sessions = self._load_raw()
            session = sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            session.agent_name = agent_name
            sessions[session_id] = session
            self._save_raw(sessions)
            return session

    def clear_messages(self, session_id: str) -> ChatSession:
        with self._lock:
            sessions = self._load_raw()
            session = sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            session.messages = []
            sessions[session_id] = session
            self._save_raw(sessions)
            return session

    @staticmethod
    def _maybe_update_title(session: ChatSession) -> None:
        if session.title == "New chat":
            user_messages = [
                m["content"] for m in session.messages if m["role"] == "user"
            ]
            if user_messages:
                session.title = user_messages[0][:48] or "New chat"
