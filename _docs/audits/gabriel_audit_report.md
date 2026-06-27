# Gabriel Codebase Audit Report

**Repository:** https://github.com/TallKid420/Gabriel
**Audited commit:** `0ec6882` ("Secuity Added") — 23 commits total
**Audit date:** 2026-06-25
**Auditor:** Abacus.AI Agent — static + execution-path analysis
**Purpose:** Phase 1 discovery for a production-grade AI knowledge base + RAG system. Establish what already exists, what is reusable, and what must be built.

> **Method:** Every claim below was verified by tracing the actual Python execution paths (imports, attribute access, function call graphs), not by reading READMEs or comments. Where the code and the documentation disagree, the code wins and the discrepancy is called out.

---

## 1. Executive Summary

Gabriel is a **two-process AI agent chat application**: a **FastAPI backend** (`api/`) that owns all logic and a **thin Streamlit UI** (`app.py`, `views/`) that talks to it over REST + SSE/WebSocket. All persistent state was recently unified onto a **single self-hosted PostgreSQL + pgvector database** (`db/`), replacing a previous mix of ChromaDB, multiple SQLite files, and a `sessions.json`. **Ollama** is the external LLM/embedding service (`bge-m3`, 1024-dim).

**Overall maturity:** This is an **early-stage, actively-refactored prototype** with a few genuinely production-quality subsystems and several half-finished or broken ones. The persistence/repository layer and the chat-agent runtime are the strongest assets. The RAG retrieval path — the single most important thing for the user's stated goal — is **broken by a one-line attribute bug**, and document (PDF/DOCX/etc.) ingestion is an unimplemented stub.

**Headline findings:**

| # | Finding | Severity |
|---|---------|----------|
| 1 | **RAG retrieval is broken.** `VectorDatabase.similarity_search()` references `self._embedding_model`, which is never defined (the property is `embeddings_model`). Every query-time embedding raises `AttributeError`. This breaks the `vector_search` agent tool **and** `MemoryService.search`. | 🔴 Critical |
| 2 | **Document processing is missing.** `daemon/ingest.py:_ingest_file()` is a stub that raises `NotImplementedError`. No PDF/DOCX/TXT/CSV/XLSX parsing exists anywhere. Only crawled HTML→markdown pages are ingested. | 🔴 Critical (for KB goal) |
| 3 | **The vector *storage* + *write* path is solid.** Schema, HNSW cosine index, `VectorRepository`, embedding generation on ingest, and the end-to-end `verify_db.py` harness all work and are well-engineered. | 🟢 Reusable |
| 4 | **No UI/API path to add knowledge.** The Memory page "Add Resources" form is a non-wired stub; there is no `POST /api/memory` ingest endpoint. The only ingestion route is the background crawler daemon. | 🟠 Major gap |
| 5 | **Only the `chat` agent type is live.** `researcher`/`engineer`/`server`/`daemon` agents exist as scaffolding in `experimental/` but are commented out of every registry. | 🟠 Partial |
| 6 | **`research.crawl_data` tool is broken** — calls `database.crawl_parallel()`, a method that does not exist on `VectorDatabase`. | 🟠 Broken |
| 7 | **Test suite is partially stale** — `TestToolRegistry` asserts 5 agent types but only `chat` is registered, so those tests fail. | 🟡 Minor |

**Recommendation in one line:** Keep and build on the `db/` repository layer, the Postgres+pgvector schema, the FastAPI service/route scaffolding, the crawl4ai crawler, and the LangGraph chat runtime. Rebuild/complete the retrieval path, document parsing, chunking strategy, and the ingestion API/UI.

---

## 2. Technology Stack Analysis

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.10+ (`from __future__`, `X | Y` unions, `dataclass`) | Single-language backend |
| Backend framework | **FastAPI** (`api/app.py`) + `uvicorn[standard]` | CORS open `*`; routers for agents/chat/sessions/tools/memory/permissions/ws |
| UI framework | **Streamlit** (`app.py`, `views/`) | Thin presentation client via `GabrielAPIClient`; multipage `st.navigation` |
| Agent framework | **LangChain + LangGraph** | `langchain.agents.create_agent`, `langgraph` ≥0.1.20 |
| LLM / Embeddings | **Ollama** via `langchain-ollama` | `ChatOllama` for chat; `OllamaEmbeddings(bge-m3)` for vectors |
| Database | **PostgreSQL + pgvector** | `psycopg[binary]` v3, `psycopg_pool`, `pgvector` adapter (optional) |
| Conversation memory | **LangGraph `PostgresSaver`** | Checkpoint tables in same DB |
| Web crawling | **crawl4ai** (`AsyncWebCrawler`) | In `experimental/crawler/` |
| Web search | **ddgs** (DuckDuckGo) | Used by `research` tool + discovery |
| Async HTTP | `aiohttp`, `httpx` | Downloader + API client |
| Misc | `tldextract`, `nest_asyncio`, `PyYAML`, `python-dotenv`, `rich`, `docker` | `docker` only used by experimental sandbox |

**Notable absences for a RAG/KB system:** no text-splitter library with token/overlap awareness (`langchain-text-splitters` not present — chunking is hand-rolled), **no PDF/DOCX parsing library** (`pypdf`, `pdfminer`, `python-docx`, `unstructured` all absent), no reranker, no hybrid/BM25 search, no eval framework.

**Architecture diagram (verified call paths):**

```
Streamlit UI (app.py, views/)
   │  REST + SSE/WebSocket  (api/client.py: GabrielAPIClient)
   ▼
FastAPI backend (api/app.py)
   ├─ routes/ ─ services/ (agent, session, memory, tool, config)
   │     │
   │     ├─ AgentService → AgentExecutor → AgentFactory → ChatAgent
   │     │        └─ LangGraph create_agent(ChatOllama, tools, PostgresSaver)
   │     ├─ SessionService → db.repositories.SessionRepository
   │     └─ MemoryService  → daemon.database.VectorDatabase → VectorRepository
   │
   └─ db/ (pool, repositories, schema, migrate, checkpointer)  ── PostgreSQL + pgvector

Crawler daemon (daemon/heartbeat.py)         [separate process]
   ├─ crawl loop  → experimental/crawler/crawler.py (crawl4ai) → raw JSON on disk
   └─ ingest loop → daemon/ingest.py → VectorDatabase.process_and_store_document → embeddings → documents table
```

---

## 3. Component-by-Component Assessment

Legend: 🟢 **Complete** · 🟡 **Partial** · 🔵 **Prototype** · 🔴 **Broken** · ⚪ **Missing**

### 3.1 Agent Systems — 🟡 Partial

**Files:** `agents/base_agent.py`, `agents/factory.py`, `agents/registry.py`, `agents/executor.py`, `agents/types/chat_agent.py`, `experimental/agents/**`

- **`BaseAgent`** — dataclass with full config (provider, model, temperature, tools, system_prompt, agent_id), `from_dict` polymorphic dispatch, `validate()`. Clean. 🟢
- **`ChatAgent`** — the only fully-wired agent. Builds a LangGraph runtime via `create_agent(ChatOllama, wrapped_tools, PostgresSaver checkpointer)`. Supports `run()` and `run_stream()`. Syncs per-agent tool enablement to DB. **Functional.** 🟢
- **`AgentFactory`** — `spawn()` with deterministic `agent_id` (uuid5 of name) and an in-process cache. 🟢
- **`AgentExecutor`** — `execute()` / `execute_stream()`, type-contract validation, config translation. 🟢
- **Multi-agent types** (`researcher`, `engineer`, `server`, `daemon`) — full class files exist in `experimental/agents/`, but they are **commented out** in `AGENT_REGISTRY`, `AGENT_TYPE_MAP`, and `AgentExecutor.TYPE_CONTRACTS`. They cannot be spawned. 🔵 Prototype (scaffolded, disabled).

**Verdict:** Single-agent (chat) runtime is **Complete and reusable**. The advertised multi-agent system is **Prototype** — structurally present, not active.

### 3.2 Memory Systems — Split verdict

| Sub-component | Status | Evidence |
|---|---|---|
| **Conversation memory** (chat history / threads) | 🟢 Complete | `db/checkpointer.py` → LangGraph `PostgresSaver`, keyed by `thread_id`=session id. Wired into every agent's `create_agent(checkpointer=...)`. Plus durable `messages` table via `SessionRepository`. |
| **Knowledge-base memory — storage** | 🟢 Complete | `documents` table + `VectorRepository.insert_documents/list/delete/count`. |
| **Knowledge-base memory — retrieval** | 🔴 Broken | `VectorDatabase.similarity_search()` (the only app-level read API) is broken — see §3.6. |

### 3.3 Database Systems — 🟢 Complete (strongest subsystem)

**Files:** `db/schema.sql`, `db/repositories.py`, `db/pool.py`, `db/config.py`, `db/migrate.py`, `db/checkpointer.py`, `scripts/verify_db.py`

- **Connection pool** (`db/pool.py`) — process-wide `psycopg_pool.ConnectionPool` singleton, `autocommit=True`, `prepare_threshold=0`, `dict_row`, best-effort pgvector adapter registration. Correctly configured for both `PostgresSaver` and pgvector. 🟢
- **Repositories** (`db/repositories.py`, 768 lines) — `SessionRepository`, `AgentRepository`, `LinkRepository`, `VectorRepository`. Production-grade: parameterized SQL, transactions, `SELECT ... FOR UPDATE SKIP LOCKED` for concurrent crawl/ingest claims, exponential backoff + jitter retry logic, `ON CONFLICT` upserts. 🟢
- **Migration** (`db/migrate.py`) — idempotent; enables `vector` extension, substitutes `__EMBEDDING_DIM__`, applies schema, sets up checkpoint tables. 🟢
- **Verification** (`scripts/verify_db.py`) — exercises all four repositories + FastAPI endpoints against a real DB with a fake embedder. Notably, this script tests `VectorRepository.search()` **directly**, bypassing the broken `VectorDatabase.similarity_search()` — which is why the retrieval bug never surfaced in CI.

**Verdict:** **Keep as-is.** This layer is well-architected and is the foundation to build the production KB on.

### 3.4 Database Schema Analysis

From `db/schema.sql` (single source of truth; `EMBEDDING_DIM` injected at migration time):

| Table | Purpose | Key columns / indexes |
|-------|---------|----------------------|
| `sessions` | Chat sessions | `id PK`, `seq BIGSERIAL`, `title`, `created_at`, `agent_name`; idx on `seq` |
| `messages` | Chat history | `session_id FK→sessions ON DELETE CASCADE`, `position`, `role`, `content`; `UNIQUE(session_id, position)` |
| `agents` | Registered agents | `agent_id PK`, `name`, `updated_at` |
| `agent_tools` | Per-agent tool enablement | `PK(agent_id, tool_id)`, `enabled BOOL` |
| `links` | Crawler queue | `url UNIQUE`, `crawl_status`, `ingest_status`, `retry_count`, `next_retry_at`, `raw_path`, failure metadata; idxs on crawl/ingest status + retry |
| `documents` | **Vector KB** | `id UUID PK`, `url`, `content`, `metadata JSONB`, `embedding vector(DIM)`; **HNSW** index `vector_cosine_ops`; idx on `url` |
| `checkpoints*` | LangGraph checkpoints | Managed by `PostgresSaver.setup()` |

**Schema observations for the KB build:**
- `documents` is a flat chunk table. There is **no `sources`/`documents`/`chunks` separation** (a single ingested file = many `documents` rows correlated only by `metadata.url`). For a production KB you will likely want a parent `sources` table + a `chunks` child table (dedupe, re-ingest, per-source deletion, versioning).
- No `ON DELETE` semantics tie chunks to a logical source; deletion is by chunk `id` list.
- Metadata is schemaless JSONB (`url`, `chunk_number`, `title`, `summary`, `crawled_at`, `source`).
- HNSW cosine index is appropriate and production-ready. `EMBEDDING_DIM` is baked into the column at migrate time — changing models requires re-migration.

### 3.5 Crawl4AI Integration — 🟡 Partial (functional but quarantined)

**Files:** `experimental/crawler/crawler.py`, `daemon/heartbeat.py`, `daemon/ingest.py`, `daemon/url_parser/*`, `config/crawler.yaml`

- crawl4ai **is** installed (`requirements.txt`) and **actively used**: `AsyncWebCrawler`, `BrowserConfig` (headless, `--no-sandbox`), `CrawlerRunConfig(cache_mode=BYPASS)`.
- `crawl_heartbeat()` is a real, careful implementation: backpressure check, batch claim, file-vs-page routing, multi-browser-instance distribution, concurrent sub-batching, 404→strip-query-param requeue, retryable HTTP status handling, markdown extraction → raw JSON envelope on disk. 🟢 for the page path.
- Driven by `daemon/heartbeat.py` async loops (crawl + ingest) with signal handling and claimed-row release on shutdown. 🟢
- **Caveats:** lives under `experimental/`; `config/crawler.yaml` still references **stale** `db_path: database/links.sqlite` and `chroma_db_path: database/chroma` (dead config, ignored by the Postgres backend) and points `ollama_base_url` at a personal host (`jcs-macbook-pro`). The downloader saves binary files but ingestion of them is unimplemented (§3.7).

**Verdict:** The crawling engine is **reusable and fairly complete for HTML pages**; treat config as needing cleanup and the experimental location as needing promotion/stabilization.

### 3.6 Vector Search & Embedding Pipelines

**Files:** `daemon/database.py` (`VectorDatabase`), `db/repositories.py` (`VectorRepository`), `executor/tools/database/search.py`, `executor/tools/research/tools.py`, `api/services/memory_service.py`

#### Embedding generation (ingest / write path) — 🟡 Partial (works, but naive)
- `VectorDatabase.process_and_store_document(url, markdown)` → `chunk_text()` → `process_chunk()` → `insert_chunks_local()` → `OllamaEmbeddings.embed_documents()` → `VectorRepository.insert_documents()`. This path **works** and correctly uses the `embeddings_model` property.
- **Chunking is primitive:** `chunk_text()` is a fixed 5000-character window split with **no overlap, no token/sentence boundaries, no structural awareness**. "Title/summary" = first markdown heading + first 200 chars. Not adequate for production retrieval quality.
- Concurrency guarded by an asyncio semaphore (2) for Ollama calls.

#### Vector search (query / read path) — 🔴 **Broken**
```python
# daemon/database.py, line ~112, inside similarity_search()
embedding = self._embedding_model.embed_query(query)   # ❌ self._embedding_model never defined
```
The class defines `self._embeddings`, `self._embedding_model_name`, and a property `embeddings_model` — but **not** `self._embedding_model`. Every call raises `AttributeError`, caught and re-raised as `"Vector DB Search Error: ..."`.

**Blast radius:**
- `executor/tools/database/search.py::vector_search` (the RAG tool agents call) → returns an error string, never retrieves.
- `api/services/memory_service.py::MemoryService.search()` → fails.
- The low-level `VectorRepository.search()` (cosine `<=>`, HNSW) is **correct** and proven by `verify_db.py`; only the `VectorDatabase` wrapper that produces the *query embedding* is broken. **One-line fix** (`self._embedding_model` → `self.embeddings_model`).

#### Other vector entry points
- `executor/tools/research/tools.py::crawl_data` calls `database.crawl_parallel(...)` — **no such method exists** on `VectorDatabase`. 🔴 Broken tool.
- `executor/tools/database/search.py::graph_search` — hardcoded placeholder string. 🔵 Prototype.

**Verdict:** Storage + ANN index = Complete; ingest embedding = Partial (naive chunking); **query-time retrieval = Broken** at the application layer despite a working DB primitive underneath.

### 3.7 Document Processing (PDF / DOCX / TXT) — ⚪ Missing

- `daemon/ingest.py::_ingest_file()` is an explicit stub: raises `NotImplementedError`, with a TODO listing the intended per-type handling (pdf→pdfminer/pymupdf, docx→python-docx, txt/md direct, csv/xlsx→rows, html→strip, json→flatten). The ingest loop catches this and marks such items as non-retryable failures.
- `daemon/url_parser/downloader.py` **downloads** files by Content-Type/extension into dated folders (pdf, docx, csv, xlsx, etc.) — but nothing ever parses them.
- `executor/tools/files/{find_file,search_documents,semantic_search}.py` are **0-byte empty files** — the "file search / semantic file search" tools advertised by the folder structure do not exist.
- No PDF/DOCX parsing dependency is installed.

**Verdict:** Document ingestion must be **built from scratch**. Only crawled-HTML-as-markdown is supported today.

### 3.8 UI Components — 🟡 Partial

**Files:** `app.py`, `views/{chat,server,models,sessions,agents,memory,tools,settings}.py`, `api/client.py`

- Streamlit multipage app (8 pages) acting as a thin client; backend reachability banner; SSE/WS streaming chat. Most pages render backend data through `GabrielAPIClient`.
- **`views/memory.py` "Add Resources" form is a stub:** on submit it shows *"Backend ingestion endpoint is not wired yet (tracked in the technical-debt list)."* It does not enqueue URLs or upload files. The "View Stored Memories" tab works (lists/deletes via `/api/memory`).
- Other pages (chat, sessions, agents, tools, server, settings) are functional against existing endpoints.

**Verdict:** UI shell is reusable; the **knowledge-ingestion UI is missing/stubbed** and must be wired to a new ingest endpoint.

### 3.9 Existing Ingestion Pipelines — 🟡 Partial

Two conceptual ingestion routes; only one partially works:
1. **Crawler daemon route (page content):** URL enqueued in `links` → `crawl_heartbeat` (crawl4ai) → raw JSON → `ingest_heartbeat` → `VectorDatabase.process_and_store_document` → embeddings → `documents`. **Works for HTML pages** when Ollama + Postgres + the daemon are running. File content → `NotImplementedError`.
2. **Direct/API route:** `MemoryService.add_document(url, markdown)` exists **but is not exposed by any route** (the memory router only has GET list + DELETE). The UI form that would feed it is a stub.

Also note: **no URL-enqueue API** — there is no exposed endpoint for a user/UI to push URLs into the `links` queue; population paths are the `LinkRepository.add_urls` API (used by tests/daemon) and tools, not an HTTP route.

Stray debug `print("1")/("1 done")/("2")` statements remain in `daemon/ingest.py`.

### 3.10 API Structure — 🟢 Mostly Complete (with one gap)

**Files:** `api/app.py`, `api/routes/*`, `api/services/*`, `api/dependencies.py`, `api/schemas.py`, `api/websocket.py`, `api/client.py`

- FastAPI app with `/health` and routers: **agents, chat, sessions, tools, memory, permissions, websocket**. CORS wide open. DI via `Depends` providers; clean service layer wrapping the core.
- **Chat:** `POST /api/chat` (sync) + `POST /api/chat/stream` (SSE) + `/ws/chat` (WebSocket). Streaming uses a thread + `queue.SimpleQueue` to interleave tokens and tool/permission events; `AgentService` normalizes LangChain/LangGraph event shapes. Solid. 🟢
- **Sessions / Agents / Tools:** CRUD-style routes backed by repositories/config. 🟢
- **Memory:** `GET /api/memory` (grouped list + count), `DELETE /api/memory`. **No POST/ingest route.** 🟡
- **Permissions:** approval-gate respond endpoint backing the security flow. 🟢

**Verdict:** Reusable, well-structured API surface. **Gap: ingestion endpoints** (enqueue URL, upload document, trigger re-index).

### 3.11 Security / Tool Permission Layer — 🟡 Partial (recent, fairly complete)

**Files:** `security/{permission_tool,middleware,gate,permissions,audit,permission_tool}.py`, `api/routes/permissions.py`

- `wrap_tools()` wraps every tool in `PermissionWrappedTool`, enforcing ALLOW/ASK/DENY via a `permission_manager`. ASK emits a `permission_request` SSE event and blocks on an approval gate until the user responds via `POST /api/permissions/{id}/respond`. Actions are written to an audit log (`audit.jsonl`). 🟢 design.
- Newest commit ("Secuity Added"); `security/models.py` is empty (0 bytes). Maturity is recent — functional for the chat tool path, but lightly tested.

### 3.12 Tool Catalog — mixed

`executor/toolhandler.py` auto-discovers tools by scanning `executor/tools/<category>/*.py` for objects with `.name`+`.invoke` (LangChain `@tool`), with mtime-based cache invalidation. 🟢 mechanism.

| Category | Status | Notes |
|---|---|---|
| `system` (16 tools) | 🟢 Implemented | file/dir ops, processes, shell, disk, ping, env |
| `email` (13 tools + IMAP client) | 🟡 Implemented, recent | full IMAP/SMTP suite; commit "Email/Calendar/Files IMAP started" |
| `math`, `text`, `time`, `random`, `utility` | 🟢 Implemented | small, functional |
| `database/search.py` | 🟡/🔴 | `vector_search` depends on broken `similarity_search`; `graph_search` is a placeholder |
| `research/tools.py` | 🔴 Broken | `crawl_data` calls nonexistent `crawl_parallel` |
| `files/` (find_file, search_documents, semantic_search) | ⚪ Missing | **all 0-byte empty** |
| `calendar/` (9 tools) | ⚪ Missing | **all 0-byte empty** |

### 3.13 Tests — 🟡 Partial / partly stale

`tests/test_core.py` covers config loader, URL normalizer (thorough), and `BaseAgent` stream/validate round-trips (mocked, no Ollama) — these should pass. **However**, `TestToolRegistry` asserts the registry contains `{chat, engineer, researcher, server, daemon}`, while only `chat` is registered → those assertions **fail** against current code. `verify_db.py` is a strong integration harness but requires a live Postgres. No tests cover the retrieval path (which is why bug #1 is latent).

---

## 4. Dependency Analysis

**Declared (`requirements.txt`):** `aiohttp, crawl4ai, ddgs, docker, fastapi>=0.115, httpx, langchain, langchain-core>=0.2, langchain-ollama>=0.1, langgraph>=0.1.20, langgraph-checkpoint-postgres, nest_asyncio, pgvector, psycopg[binary], psycopg_pool, pydantic>=2.8, python-dotenv, PyYAML>=6, rich>=14, streamlit>=1.36, tldextract, uvicorn[standard]>=0.30`.

**Observations:**
- **No version pins** on several core libs (`langchain`, `aiohttp`, `crawl4ai`, `httpx`, `ddgs`) — reproducibility risk, especially with the fast-moving LangChain/LangGraph APIs (`langchain.agents.create_agent` is a relatively new/beta surface; `LangChainBetaWarning` is suppressed in agent code).
- **Missing for the stated KB/RAG goal:** document parsers (`pypdf`/`pymupdf`, `python-docx`, `openpyxl`, `unstructured`), a real text splitter (`langchain-text-splitters`), optional reranker/hybrid-search libs, and a test/eval stack beyond `pytest` (pytest itself isn't even in requirements, only configured in `pytest.ini`).
- `docker` is declared but only used by `experimental/sandbox` (not in the main path).
- External runtime deps: a reachable **Ollama** server (embeddings + chat) and **PostgreSQL 13+ with pgvector**. The committed configs hardcode a personal Ollama host (`jcs-macbook-pro:11434`) — environment-specific, must be parameterized.

---

## 5. Reusable vs Rebuild Recommendations

### 5.1 Keep & build on (reusable assets) 🟢
- **`db/` package in full** — pool, repositories, schema, migration, checkpointer. This is production-quality and should anchor the new KB.
- **PostgreSQL + pgvector + HNSW** as the vector store (avoid reintroducing Chroma).
- **FastAPI service/route/DI scaffolding** and the **streaming chat stack** (SSE + WS + event normalization).
- **LangGraph chat-agent runtime** (`ChatAgent`, `AgentExecutor`, `AgentFactory`, `PostgresSaver` conversation memory).
- **crawl4ai crawler engine** (`experimental/crawler/crawler.py`) and the **downloader/URL-normalizer** utilities — page crawling, retry, backpressure, and dedupe are already done well.
- **Tool auto-discovery registry** and the **permission/audit security layer**.
- **`verify_db.py`** harness pattern for integration testing.

### 5.2 Fix / enhance (do not rebuild) 🟡
- **Fix the retrieval bug** (`similarity_search`: `self._embedding_model` → `self.embeddings_model`) and add a regression test — this single fix restores RAG.
- **Fix or remove `research.crawl_data`** (`crawl_parallel` missing).
- **Replace naive `chunk_text`** with a token-aware splitter with overlap and structural boundaries; enrich chunk metadata.
- **Promote the crawler** out of `experimental/`; clean `config/crawler.yaml` (drop dead `sqlite`/`chroma` paths; externalize Ollama URL).
- **Evolve the `documents` schema** toward a `sources` + `chunks` model for dedupe, re-ingest, per-source deletion, and versioning.
- **Update the stale tests** (registry expectations) and add retrieval/ingestion coverage.
- Remove stray debug `print` statements in `daemon/ingest.py`.

### 5.3 Build new (missing) ⚪🔴
- **Document processing pipeline** — implement `_ingest_file` for PDF/DOCX/TXT/CSV/XLSX/HTML/JSON (add parser deps). This is the biggest net-new build for the KB goal.
- **Ingestion API + UI** — `POST /api/memory` (and/or `/api/ingest`) to enqueue URLs and accept file uploads; wire the Streamlit "Add Resources" form to it; expose a URL-enqueue endpoint over the `links` queue.
- **Retrieval quality layer** — hybrid (vector + keyword/BM25) search, optional reranking, citations/source attribution, and a real implementation of the `files/` semantic-search tools (currently empty).
- **`graph_search`** — implement or remove the placeholder.
- **Multi-agent activation** — if needed, finish and register the `researcher`/`engineer` agents (currently disabled scaffolding).
- **RAG evaluation harness** — retrieval precision/recall and answer-faithfulness metrics (none exist).

---

## 6. Component Status Matrix (at a glance)

| Capability | Status | One-line justification |
|---|---|---|
| Agent system (chat) | 🟢 Complete | LangGraph runtime, factory, executor, DB-backed checkpoints all wired |
| Agent system (multi-type) | 🔵 Prototype | researcher/engineer/etc. scaffolded in `experimental/`, disabled in registries |
| Conversation memory | 🟢 Complete | LangGraph `PostgresSaver` + `messages` table |
| KB vector storage | 🟢 Complete | `documents` table, `VectorRepository`, HNSW cosine index |
| KB vector retrieval | 🔴 Broken | `similarity_search` references undefined `self._embedding_model` |
| Database layer | 🟢 Complete | Pool + 4 repositories + idempotent migration + verify script |
| Crawl4AI integration | 🟡 Partial | Page crawl complete; in `experimental/`; stale config; file path unfed |
| Document processing (PDF/DOCX/TXT) | ⚪ Missing | `_ingest_file` raises `NotImplementedError`; no parsers installed |
| Embedding pipeline (ingest) | 🟡 Partial | Works via OllamaEmbeddings; chunking is naive fixed-window |
| Embedding pipeline (query) | 🔴 Broken | Same attribute bug as retrieval |
| UI (shell + chat/sessions) | 🟡 Partial | Functional pages; ingestion form is a stub |
| Ingestion pipeline | 🟡 Partial | Crawler→ingest works for pages; no API/UI trigger; no file ingest |
| API structure | 🟢 Complete* | Full router/service surface; *missing ingestion endpoints |
| Security/permissions | 🟡 Partial | ALLOW/ASK/DENY gate + audit + SSE approval; recent, lightly tested |
| File/semantic-search tools | ⚪ Missing | `files/*.py` are empty |
| Calendar tools | ⚪ Missing | `calendar/*.py` are empty |
| Test suite | 🟡 Partial | Config/URL/agent tests OK; registry tests stale/failing |

---

## 7. Appendix — Key Evidence Pointers

- Retrieval bug: `daemon/database.py` — property `embeddings_model` (l.~91) vs. use of `self._embedding_model.embed_query` (l.~112). Write path `insert_chunks_local` correctly uses `self.embeddings_model` (l.~205).
- Document-ingest stub: `daemon/ingest.py::_ingest_file` → `raise NotImplementedError`.
- Empty tool files: `executor/tools/files/{find_file,search_documents,semantic_search}.py` and `executor/tools/calendar/*.py` (all 0 bytes).
- Broken research tool: `executor/tools/research/tools.py::crawl_data` → `database.crawl_parallel(...)` (undefined).
- Unwired UI ingest: `views/memory.py` submit handler prints "Backend ingestion endpoint is not wired yet".
- Memory API has no POST: `api/routes/memory.py` (only GET + DELETE); `MemoryService.add_document` exists but is unexposed.
- Disabled agents: commented entries in `agents/registry.py`, `agents/base_agent.py::AGENT_TYPE_MAP`, `agents/executor.py::TYPE_CONTRACTS`.
- Stale tests: `tests/test_core.py::TestToolRegistry.test_registry_contains_expected_types` expects 5 types; only `chat` registered.
- Stale crawler config: `config/crawler.yaml` (`db_path: database/links.sqlite`, `chroma_db_path: database/chroma`, `ollama_base_url: http://jcs-macbook-pro:11434`).

---

*End of report.*
