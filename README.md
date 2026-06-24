# Gabriel

Gabriel is an AI agent chat application with session management, configurable agents,
and an optional daemon/server control page.

> **Architecture (after backend extraction):** Gabriel now runs as **two processes** — a
> **FastAPI backend** (`api/`) that owns all agent, tool, memory, session, and
> orchestration logic, and a **thin Streamlit UI** (`app.py`, `views/`) that talks to the
> backend over REST + WebSocket/SSE. See [`docs/`](docs/) for the full migration write-up
> (architecture assessment, migration plan, backend design, phased rollout, validation,
> and tech debt).

## What it does

- Provides a chat interface powered by configurable agents defined in `config/agents.yaml`
- Saves chat sessions in `database/sessions.json`
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
- `daemon/` - Daemon process and database support (unchanged core)
- `executor/` - Tool handling and provider integrations (unchanged core)
- `database/` - Persistent session storage and checkpoints
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

- Saved sessions are stored in `database/sessions.json`
- The app uses `agents.executor.AgentExecutor` to run agent conversations and stream responses
- The chat UI supports formatted JSON and tool output display
