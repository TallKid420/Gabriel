from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import uuid

import yaml


@dataclass
class AgentConfig:
    name: str
    type: str
    provider: str
    endpoint: str
    timeout_seconds: int
    temperature: float
    model: str
    system_prompt: str
    # tools: list[str] = field(default_factory=list)
    schedule: str | None = None
    trigger: str | None = None
    enabled: bool = True
    agent_id: str | None = None
    mailbox_id: str | None = None
    parent_id: str | None = None
    spawn_depth: int = 0
    max_children: int = 5
    max_spawn_depth: int = 3
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlerConfig:
    # ── Paths ─────────────────────────────────────────────────────────────────
    db_path:    Path = Path("data/links.sqlite")
    raw_dir:    Path = Path("data/raw")
    files_dir:  Path = Path("data/files")

    # ── Ollama / vector DB ────────────────────────────────────────────────────
    ollama_base_url:   str = ""
    embedding_model:   str = "bge-m3"
    llm_model:         str = "mistral:v0.3"
    chroma_db_path:    Path = Path("data/chroma")

    # ── Crawl loop ────────────────────────────────────────────────────────────
    crawl_interval_sec:          float = 60.0
    crawl_batch_size:            int   = 10
    browser_instances:           int   = 1
    max_concurrent_per_instance: int   = 3
    request_timeout_seconds:     int   = 60

    # ── Ingest loop ───────────────────────────────────────────────────────────
    ingest_interval_sec: float = 15.0
    ingest_batch_size:   int   = 10

    # ── File handling ─────────────────────────────────────────────────────────
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".pdf", ".txt", ".md", ".html", ".htm",
        ".csv", ".json", ".xml", ".docx", ".xlsx",
    ])

    # ── Backpressure (optional) ───────────────────────────────────────────────
    # If set, crawling pauses when this many raw files are waiting for ingest.
    # Remove or set to null in YAML to disable.
    backpressure_threshold: int | None = None

    # ── Daemon lifecycle ──────────────────────────────────────────────────────
    # If true, the daemon keeps running after the UI process exits.
    # If false, the daemon stops when the UI stops.
    keep_alive_on_ui_exit: bool = False

@dataclass
class FileToolConfig:
    root_dirs: list[str] = field(default_factory=lambda: ["~/Documents", "."])
    allowed_extensions: list[str] = field(default_factory=lambda: [".txt", ".md", ".pdf", ".docx"])
    max_search_results: int = 100
    enabled: bool = True


@dataclass
class EmailToolConfig:
    provider: str = "imap"
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 465
    username: str = ""
    password: str = ""
    default_folder: str = "INBOX"
    use_ssl: bool = True
    enabled: bool = True


@dataclass
class CalendarToolConfig:
    provider: str = "ics"
    ics_path: str = ""
    timezone: str = "America/Los_Angeles"
    default_calendar_id: str = "primary"
    enabled: bool = True


@dataclass
class ToolConfig:
    files: FileToolConfig = field(default_factory=FileToolConfig)
    email: EmailToolConfig = field(default_factory=EmailToolConfig)
    calendar: CalendarToolConfig = field(default_factory=CalendarToolConfig)


def load(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file)
    return loaded if isinstance(loaded, dict) else {}


def _agent_from_dict(entry: dict[str, Any]) -> AgentConfig:
    known = {
        "name",
        "type",
        "provider",
        "endpoint",
        "timeout_seconds",
        "temperature",
        "model",
        "system_prompt",
        # "tools",
        "schedule",
        "trigger",
        "enabled",
        "agent_id",
        "mailbox_id",
    }
    extra = {k: v for k, v in entry.items() if k not in known}

    if not entry.get("name"):
        raise ValueError("Agent config missing name")
    if not entry.get("type"):
        raise ValueError("Agent config missing type")
    if not entry.get("provider"):
        raise ValueError("Agent config missing provider")
    if not entry.get("model"):
        raise ValueError("Agent config missing model")
    if int(entry.get("timeout_seconds", 60)) <= 0:
        raise ValueError("timeout_seconds must be > 0")

    agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(entry["name"])))

    return AgentConfig(
        name=str(entry["name"]),
        type=str(entry["type"]),
        provider=str(entry["provider"]),
        endpoint=str(entry.get("endpoint", "http://localhost:11434")),
        temperature=float(entry.get("temperature", 0.0)),
        timeout_seconds=int(entry.get("timeout_seconds", 60)),
        model=str(entry["model"]),
        system_prompt=str(entry.get("system_prompt", "")),
        # tools=list(entry.get("tools", [])),
        schedule=entry.get("schedule"),
        trigger=entry.get("trigger"),
        enabled=bool(entry.get("enabled", True)),
        agent_id=agent_id,
        mailbox_id=agent_id,
        extra=extra,
    )


def _extract_entries(raw: dict[str, Any], section_name: str) -> list[dict[str, Any]]:
    section = raw.get(section_name, {})
    if isinstance(section, list):
        return [entry for entry in section if isinstance(entry, dict)]
    if isinstance(section, dict):
        agents_list = section.get("agents")
        if isinstance(agents_list, list):
            return [entry for entry in agents_list if isinstance(entry, dict)]
        return [
            {"name": key, **value}
            for key, value in section.items()
            if key != "agents" and isinstance(value, dict)
        ]
    return []


def load_agents(path: str | Path) -> list[AgentConfig]:
    return load_custom_agents(path)


def load_system_agents(path: str | Path) -> list[AgentConfig]:
    raw = load(path)
    entries = _extract_entries(raw, "system_agents")
    return [_agent_from_dict(entry) for entry in entries if entry.get("enabled", True)]


def load_custom_agents(path: str | Path) -> list[AgentConfig]:
    raw = load(path)
    entries = _extract_entries(raw, "custom_agents")
    return [_agent_from_dict(entry) for entry in entries if entry.get("enabled", True)]


def load_tool_config(path: str | Path = "config/tool_config.yaml") -> ToolConfig:
    """Load tool configuration from YAML file."""
    raw = load(path)
    tools_section = raw.get("tools", {})
    
    files_data = tools_section.get("files", {})
    email_data = tools_section.get("email", {})
    calendar_data = tools_section.get("calendar", {})
    
    files_config = FileToolConfig(
        root_dirs=files_data.get("root_dirs", ["~/Documents", "."]),
        allowed_extensions=files_data.get("allowed_extensions", [".txt", ".md", ".pdf"]),
        max_search_results=int(files_data.get("max_search_results", 100)),
        enabled=bool(files_data.get("enabled", True)),
    )
    
    email_config = EmailToolConfig(
        provider=str(email_data.get("provider", "imap")),
        imap_host=str(email_data.get("imap_host", "")),
        imap_port=int(email_data.get("imap_port", 993)),
        smtp_host=str(email_data.get("smtp_host", "")),
        smtp_port=int(email_data.get("smtp_port", 465)),
        username=str(email_data.get("username", "")),
        password=str(email_data.get("password", "")),
        default_folder=str(email_data.get("default_folder", "INBOX")),
        use_ssl=bool(email_data.get("use_ssl", True)),
        enabled=bool(email_data.get("enabled", True)),
    )
    
    calendar_config = CalendarToolConfig(
        provider=str(calendar_data.get("provider", "ics")),
        ics_path=str(calendar_data.get("ics_path", "")),
        timezone=str(calendar_data.get("timezone", "America/Los_Angeles")),
        default_calendar_id=str(calendar_data.get("default_calendar_id", "primary")),
        enabled=bool(calendar_data.get("enabled", True)),
    )
    
    return ToolConfig(files=files_config, email=email_config, calendar=calendar_config)


def load_file_tool_config(
    path: str | Path = "config/tool_config.yaml"
) -> FileToolConfig:

    return load_tool_config(path).files

def load_email_tool_config(
    path: str | Path = "config/tool_config.yaml"
) -> EmailToolConfig:

    return load_tool_config(path).email

def load_calendar_tool_config(
    path: str | Path = "config/tool_config.yaml"
) -> CalendarToolConfig:

    return load_tool_config(path).calendar