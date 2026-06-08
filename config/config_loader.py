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
    tools: list[str] = field(default_factory=list)
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
        "tools",
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
        tools=list(entry.get("tools", [])),
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
