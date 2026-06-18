# Gabriel

Gabriel is a Streamlit-based AI agent chat application with session management, configurable agents, and an optional daemon/server control page.

## What it does

- Provides a chat interface powered by configurable agents defined in `config/agents.yaml`
- Saves chat sessions in `database/sessions.json`
- Supports multiple sessions and agent selection
- Includes a server view for starting/stopping a backend daemon
- Uses the `agents`, `config`, and `executor` packages to create and manage agent workflows

## Project structure

- `app.py` - Main Streamlit app entrypoint
- `views/` - Pages for chat, server status, sessions, and settings
- `config/` - Agent config loader and manager
- `agents/` - Agent definitions, factory, and executor logic
- `daemon/` - Daemon process and database support
- `executor/` - Tool handling and provider integrations
- `database/` - Persistent session storage and checkpoints

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

Start the Streamlit app:

```powershell
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal.

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
