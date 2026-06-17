import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st
import uuid
from agents.executor import AgentExecutor
from config.config_manager import ConfigManager
from daemon.client import DaemonClient

SESSIONS_FILE = Path(__file__).resolve().parent / "database" / "sessions.json"

@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    agent_name: str | None = None
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


def current_session() -> ChatSession:
    return st.session_state.sessions[st.session_state.active_session_id]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_sessions() -> dict[str, ChatSession]:
    if not SESSIONS_FILE.exists():
        return {}
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return {
            session_id: ChatSession.from_dict(session_data)
            for session_id, session_data in data.items()
        }
    except Exception:
        return {}


def save_sessions(sessions: dict[str, ChatSession]) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        session_id: session.to_dict()
        for session_id, session in sessions.items()
    }
    SESSIONS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_state() -> None:
    if "config_manager" not in st.session_state:
        st.session_state.config_manager = ConfigManager("config/agents.yaml")
    if "agent_executor" not in st.session_state:
        st.session_state.agent_executor = AgentExecutor()
    if "daemon" not in st.session_state:
        st.session_state.daemon = DaemonClient()
    if "last_manual_agent_name" not in st.session_state:
        st.session_state.last_manual_agent_name = None
    if "sessions" not in st.session_state:
        loaded_sessions = load_sessions()
        if loaded_sessions:
            st.session_state.sessions = loaded_sessions
            st.session_state.active_session_id = next(iter(loaded_sessions.keys()))
        else:
            session_id = str(uuid.uuid4())
            st.session_state.sessions = {
                session_id: ChatSession(
                    id=session_id,
                    title="New chat",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    agent_name=None,
                    messages=[],
                )
            }
            st.session_state.active_session_id = session_id
            save_sessions(st.session_state.sessions)

def main() -> None:
    st.set_page_config(page_title="Gabriel", page_icon="💬", layout="wide")
    ensure_state()   # ← Run BEFORE navigation

    pg = st.navigation([
        st.Page("views/chat.py", title="Chat", icon="💬"),
        st.Page("views/server.py", title="Server", icon="🖥️"),
        st.Page("views/models.py", title="Models", icon="🤖"),
        st.Page("views/sessions.py", title="Sessions", icon="📋"),
        st.Page("views/agents.py", title="Agents", icon="🧠"),
        st.Page("views/memory.py", title="Memory", icon="💾"),
        st.Page("views/tools.py", title="Tools", icon="🧰"),
        st.Page("views/settings.py", title="Settings", icon="⚙️"),
    ])
    pg.run()         # ← Executes the selected page

if __name__ == "__main__":
    main()