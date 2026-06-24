"""Gabriel Streamlit front-end (thin client).

After the backend-extraction migration this module is **presentation-only**: it
no longer invokes agents, tools or the vector store directly. All business logic
lives in the FastAPI backend (``api/app.py``) and is reached through
``GabrielAPIClient``.

``ChatSession`` / ``save_sessions`` / ``load_sessions`` / ``now_iso`` are
re-exported from ``api.services.session_service`` for backwards compatibility
with any code that historically imported them from ``app``.
"""

import streamlit as st

from api.client import GabrielAPIClient
from api.services.session_service import (  # re-exported for backwards compat
    ChatSession,
    SessionService,
    now_iso,
)

# Legacy helpers kept as thin wrappers so old imports keep working. New code
# should use the API client or SessionService instead.
_session_service = SessionService()


def load_sessions() -> dict[str, ChatSession]:
    return {s.id: s for s in _session_service.list_sessions()}


def save_sessions(sessions: dict[str, ChatSession]) -> None:
    # Persistence is now owned by the backend SessionService; this wrapper keeps
    # legacy call sites functional by delegating to the same JSON store.
    _session_service._save_raw(sessions)  # noqa: SLF001 (intentional compat shim)


def get_api() -> GabrielAPIClient:
    return st.session_state.api


def ensure_state() -> None:
    """Initialise *UI-only* session state and the backend API client."""
    if "api" not in st.session_state:
        st.session_state.api = GabrielAPIClient()
    if "daemon" not in st.session_state:
        # The crawler daemon is an independent HTTP service; the UI proxies to it.
        from daemon.client import DaemonClient

        st.session_state.daemon = DaemonClient()
    if "last_manual_agent_name" not in st.session_state:
        st.session_state.last_manual_agent_name = None
    if "active_session_id" not in st.session_state:
        api = st.session_state.api
        sessions = []
        try:
            sessions = api.list_sessions()
        except Exception:
            sessions = []
        if sessions:
            st.session_state.active_session_id = sessions[0]["id"]
        else:
            try:
                created = api.create_session()
                st.session_state.active_session_id = created["id"]
            except Exception:
                st.session_state.active_session_id = None


def main() -> None:
    st.set_page_config(page_title="Gabriel", page_icon="💬", layout="wide")
    ensure_state()

    if not st.session_state.api.health():
        st.warning(
            "⚠️ Gabriel backend API is not reachable. Start it with "
            "`uvicorn api.app:app --port 8000` (set `GABRIEL_API_URL` to override "
            "the address). The UI is read-only until the backend is up."
        )

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
    pg.run()


if __name__ == "__main__":
    main()
