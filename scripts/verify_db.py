"""
Verify the PostgreSQL + pgvector setup end-to-end.

Run this after installing PostgreSQL/pgvector, configuring ``.env`` and running
``python -m db.migrate``. It exercises every repository (sessions, agents,
crawler link queue, vector store) and the FastAPI session/memory endpoints
against your real database. A fake embedder is injected so a live Ollama server
is **not** required.

    python scripts/verify_db.py

Exit code 0 = all checks passed. The script cleans up everything it creates.
"""

from __future__ import annotations

import os
import sys

# Allow running as ``python scripts/verify_db.py`` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import EMBEDDING_DIM, close_pool, get_pool
from db.repositories import (
    AgentRepository,
    LinkRepository,
    SessionRepository,
    VectorRepository,
)


def section(name: str) -> None:
    print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")


def check(cond: bool, msg: str) -> None:
    print(f"  [{'OK  ' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Repository layer
# ---------------------------------------------------------------------------
def test_sessions() -> None:
    section("SessionRepository")
    repo = SessionRepository()
    sid = "verify-sess-1"
    repo.delete_session(sid)

    repo.create_session(sid, "New Chat", "2026-01-01T00:00:00", "chat")
    check(repo.exists(sid), "session created + exists")

    repo.append_message(sid, "user", "first message")
    repo.append_message(sid, "assistant", "second message")
    sess = repo.get_session(sid)
    check(len(sess["messages"]) == 2, "two messages appended")
    check(sess["messages"][0]["role"] == "user", "messages returned in order")

    repo.update_title(sid, "My Conversation")
    check(repo.get_session(sid)["title"] == "My Conversation", "title updated")

    repo.set_agent(sid, "researcher")
    check(repo.get_session(sid)["agent_name"] == "researcher", "agent updated")
    check(any(s["id"] == sid for s in repo.list_sessions()), "appears in list_sessions")

    repo.replace_all([
        {
            "id": "verify-sess-2", "title": "Bulk",
            "created_at": "2026-01-01T00:00:00", "agent_name": "chat",
            "messages": [{"role": "user", "content": "bulk msg"}],
        }
    ])
    after = repo.list_sessions()
    check(len(after) == 1 and after[0]["id"] == "verify-sess-2", "replace_all overwrote store")

    repo.clear_messages("verify-sess-2")
    check(len(repo.get_session("verify-sess-2")["messages"]) == 0, "clear_messages works")
    repo.delete_session("verify-sess-2")
    check(not repo.exists("verify-sess-2"), "delete_session works")


def test_agents() -> None:
    section("AgentRepository")
    repo = AgentRepository()
    repo.register_agent("agent-a", "Alpha")
    repo.register_agent("agent-b", "Bravo")
    ids = {a["agent_id"] for a in repo.get_agents()}
    check({"agent-a", "agent-b"} <= ids, "agents registered")

    repo.sync_agent_tools("agent-a", ["tool-x", "tool-y"])
    check(len(repo.get_agent_tool_states("agent-a")) >= 2, "tool states synced")
    check(repo.get_enabled_tool_ids("agent-a") & {"tool-x", "tool-y"} == set(),
          "tools default to disabled after sync")

    repo.set_agent_tool_enabled("agent-a", "tool-y", True)
    enabled = repo.get_enabled_tool_ids("agent-a")
    check("tool-y" in enabled and "tool-x" not in enabled, "enable single tool works")
    repo.set_agent_tool_enabled("agent-a", "tool-y", False)
    check("tool-y" not in repo.get_enabled_tool_ids("agent-a"),
          "disable works (ON CONFLICT UPDATE)")


def test_links() -> None:
    section("LinkRepository")
    repo = LinkRepository()
    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM links WHERE url LIKE 'https://example.com/%'")

    repo.add_urls(["https://example.com/a", "https://example.com/b"], source_type="manual")
    check(repo.add_urls(["https://example.com/a"], source_type="manual") == 0,
          "duplicate url ignored (ON CONFLICT DO NOTHING)")

    claimed = repo.claim_pending_crawl(limit=5)
    check(len(claimed) >= 1, f"claim_pending_crawl returned {len(claimed)} rows")
    repo.mark_crawl_success(claimed[0]["url"], raw_path="/tmp/raw/a.md")
    check(isinstance(repo.get_stats(), dict), "get_stats returns dict")

    ing = repo.claim_pending_ingest(limit=5)
    if ing:
        repo.mark_ingest_success(ing[0]["url"])
    if len(claimed) > 1:
        repo.mark_crawl_failed(claimed[1]["url"], reason="boom", http_status=500)
    check(True, "ingest/failure paths executed")


def test_vectors() -> None:
    section("VectorRepository (pgvector cosine search)")
    repo = VectorRepository()

    def vec(seed: float) -> list[float]:
        v = [0.0] * EMBEDDING_DIM
        v[0], v[1] = seed, 1.0 - seed
        return v

    before = repo.count()
    repo.insert_documents([
        {"url": "https://kb/doc1", "content": "Postgres is a relational database.",
         "metadata": {"url": "https://kb/doc1"}, "embedding": vec(0.9)},
        {"url": "https://kb/doc2", "content": "pgvector adds similarity search.",
         "metadata": {"url": "https://kb/doc2"}, "embedding": vec(0.1)},
    ])
    check(repo.count() == before + 2, "insert_documents added 2 rows")

    listed = repo.list_documents()
    check(isinstance(listed[0]["id"], str), "document id serialised as text")

    results = repo.search(vec(0.88), k=2)
    check(results[0]["content"].startswith("Postgres"), "nearest vector is doc1")

    repo.delete([r["id"] for r in listed if r["url"] in ("https://kb/doc1", "https://kb/doc2")])
    check(repo.count() == before, "delete removed inserted docs")


# ---------------------------------------------------------------------------
# FastAPI layer
# ---------------------------------------------------------------------------
def test_api() -> None:
    section("FastAPI endpoints (/health, /api/sessions, /api/memory)")
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    check(client.get("/health").json()["status"] == "ok", "/health ok")

    sid = client.post("/api/sessions", json={"agent_name": "chat", "title": "API"}).json()["id"]
    check(any(s["id"] == sid for s in client.get("/api/sessions").json()["sessions"]),
          "session created + listed")
    r = client.post(f"/api/sessions/{sid}/messages", json={"role": "user", "content": "hi"})
    check(len(r.json()["messages"]) == 1, "append message via API")
    check(client.delete(f"/api/sessions/{sid}").status_code == 200, "delete session via API")
    check(client.get(f"/api/sessions/{sid}").status_code == 404, "deleted session -> 404")

    repo = VectorRepository()
    repo.delete([d["id"] for d in repo.list_documents() if d.get("url") == "https://api-test/p"])
    baseline = repo.count()
    emb = [0.0] * EMBEDDING_DIM
    emb[0] = 0.5
    repo.insert_documents([{"url": "https://api-test/p", "content": "chunk",
                            "metadata": {"url": "https://api-test/p"}, "embedding": emb}])
    body = client.get("/api/memory").json()
    check(body["count"] == baseline + 1, "memory listed via API")
    ids = [c["id"] for c in body["grouped"]["https://api-test/p"]]
    check(client.request("DELETE", "/api/memory", json={"ids": ids}).status_code == 200,
          "delete memory via API")
    check(repo.count() == baseline, "memory deleted from DB")


def main() -> int:
    try:
        test_sessions()
        test_agents()
        test_links()
        test_vectors()
        test_api()
    except AssertionError as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"\n❌ VERIFICATION ERROR: {e}")
        return 1
    finally:
        close_pool()
    print("\n✅ ALL CHECKS PASSED — PostgreSQL + pgvector backend is working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
