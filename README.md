# Gabriel

Gabriel is an AI agent chat application with session management, configurable agents,
and an optional daemon/server control page.

> **Architecture (after backend extraction):** Gabriel now runs as **two processes** — a
> **FastAPI backend** (`api/`) that owns all agent, tool, memory, session, and
> orchestration logic, and a **thin Streamlit UI** (`app.py`, `views/`) that talks to the
> backend over REST + WebSocket/SSE. See [`docs/`](docs/) for the full migration write-up
> (architecture assessment, migration plan, backend design, phased rollout, validation,
> and tech debt).

> **Storage (after unification):** All persistent state — chat sessions and history,
> agents, per-agent tool state, the crawler link queue, LangGraph checkpoints, and the
> vector knowledge base — lives in a **single self-hosted PostgreSQL database with the
> [pgvector](https://github.com/pgvector/pgvector) extension**. The previous mix of
> ChromaDB, multiple SQLite databases, and a `sessions.json` file has been removed.
> See **[`POSTGRES_SETUP.md`](POSTGRES_SETUP.md)** for installation, schema migration, and
> the required environment variables (e.g. `DATABASE_URL`). Ollama is still used as an
> external embedding/LLM service — it is **not** a storage backend.

## What it does

- Provides a chat interface powered by configurable agents defined in `config/agents.yaml`
- Stores chat sessions, history, agents, tools, the crawler queue, and vector memory in PostgreSQL + pgvector
- Supports multiple sessions and agent selection
- Includes a server view for starting/stopping a backend daemon
- Uses the `agents`, `config`, and `executor` packages to create and manage agent workflows

## Project structure

- `api/` - **FastAPI backend** (system of record)
  - `api/app.py` - FastAPI app, CORS, `/health`, router wiring
  - `api/routes/` - REST endpoints (agents, chat, sessions, tools, memory)
  - `api/services/` - service layer wrapping the unchanged core (agent, tool, session, memory, config)
  - `api/websocket.py` - `/ws/chat` streaming handler
  - `api/schemas.py` - Pydantic request/response models
  - `api/dependencies.py` - DI providers (service singletons)
  - `api/client.py` - `GabrielAPIClient` used by the Streamlit UI
- `app.py` - Streamlit UI entrypoint (thin presentation client)
- `views/` - Pages for chat, server status, sessions, settings (presentation only)
- `config/` - Agent config loader and manager (unchanged core)
- `agents/` - Agent definitions, factory, and executor logic (unchanged core)
- `daemon/` - Daemon process and the thin `daemon/database.py` facade over the `db` package
- `db/` - **Unified PostgreSQL + pgvector layer**: connection pool, schema, migration runner, LangGraph checkpointer, and repositories (sessions, agents, links, vectors)
- `executor/` - Tool handling and provider integrations (unchanged core)
- `docs/` - Migration documentation (assessment, plan, backend design, sequence, validation, tech debt)

## Setup

1. Create the virtual environment:

```powershell
python -m venv .venv
```

2. Activate the virtual environment:

```powershell
venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Set up PostgreSQL + pgvector and the database schema:

   Follow **[`POSTGRES_SETUP.md`](POSTGRES_SETUP.md)** to install PostgreSQL with the
   pgvector extension, create the database/role, and configure your environment. Then copy
   `.env.example` to `.env`, adjust `DATABASE_URL` if needed, and run the schema migration:

   ```bash
   cp .env.example .env
   python -m db.migrate
   ```

## Run

Gabriel now runs as two processes. Start the backend first, then the UI.

**1. Start the FastAPI backend:**

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Health probe: `http://127.0.0.1:8000/health`

**2. Start the Streamlit UI** (point it at the backend):

```bash
export GABRIEL_API_URL=http://127.0.0.1:8000   # default if unset
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal. If the backend is unreachable,
the UI shows a warning banner.

## Configuration

- `config/agents.yaml` defines available agents.
- `config/config_manager.py` loads enabled agents and handles agent settings.
- Agent behavior can be customized via YAML using provider, model, tools, prompts, timeout, and other runtime options.

## Usage

- Open the `Chat` page to send messages and receive streamed assistant replies
- Manage sessions on the `Sessions` page
- Start and stop the daemon under the `Server` page

## Notes

- All state (sessions, history, agents, tools, crawler queue, checkpoints, and vector memory) is stored in PostgreSQL + pgvector — see [`POSTGRES_SETUP.md`](POSTGRES_SETUP.md)
- The app uses `agents.executor.AgentExecutor` to run agent conversations and stream responses
- The chat UI supports formatted JSON and tool output display
