# tests/test_core.py
"""
Minimal feedback-loop test suite for Gabriel.
Covers: config loader, tool registry discovery, URL normalizer, agent stream round-trip.
Run with: pytest tests/test_core.py -v
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ═════════════════════════════════════════════════════════════════════════════
# 1. Config Loader
# ═════════════════════════════════════════════════════════════════════════════

class TestConfigLoader:

    def test_load_returns_dict(self, tmp_path):
        from config.config_loader import load
        p = _write_yaml(tmp_path, "cfg.yaml", {"key": "value"})
        result = load(p)
        assert result == {"key": "value"}

    def test_load_missing_file_raises(self, tmp_path):
        from config.config_loader import load
        with pytest.raises(FileNotFoundError):
            load(tmp_path / "nonexistent.yaml")

    def test_load_empty_file_returns_empty_dict(self, tmp_path):
        from config.config_loader import load
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        assert load(p) == {}

    def test_load_custom_agents_parses_correctly(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {
                        "name": "test-chat",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                        "endpoint": "http://localhost:11434",
                        "timeout_seconds": 30,
                        "temperature": 0.5,
                        "system_prompt": "You are a test agent.",
                        "enabled": True,
                    }
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        agents = load_custom_agents(p)
        assert len(agents) == 1
        a = agents[0]
        assert a.name == "test-chat"
        assert a.type == "chat"
        assert a.provider == "ollama"
        assert a.model == "llama3"
        assert a.temperature == 0.5
        assert a.enabled is True

    def test_load_custom_agents_skips_disabled(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {
                        "name": "active",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                        "enabled": True,
                    },
                    {
                        "name": "inactive",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                        "enabled": False,
                    },
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        agents = load_custom_agents(p)
        assert len(agents) == 1
        assert agents[0].name == "active"

    def test_agent_config_missing_name_raises(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {"type": "chat", "provider": "ollama", "model": "llama3"}
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        with pytest.raises(ValueError, match="missing name"):
            load_custom_agents(p)

    def test_agent_config_invalid_timeout_raises(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {
                        "name": "bad-agent",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                        "timeout_seconds": -1,
                    }
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        with pytest.raises(ValueError, match="timeout_seconds"):
            load_custom_agents(p)

    def test_agent_id_is_deterministic(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {
                        "name": "stable-agent",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                    }
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        a1 = load_custom_agents(p)[0]
        a2 = load_custom_agents(p)[0]
        assert a1.agent_id == a2.agent_id

    def test_extra_fields_captured(self, tmp_path):
        from config.config_loader import load_custom_agents
        data = {
            "custom_agents": {
                "agents": [
                    {
                        "name": "extra-agent",
                        "type": "chat",
                        "provider": "ollama",
                        "model": "llama3",
                        "output_dir": "/tmp/reports",
                    }
                ]
            }
        }
        p = _write_yaml(tmp_path, "agents.yaml", data)
        agent = load_custom_agents(p)[0]
        assert agent.extra.get("output_dir") == "/tmp/reports"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Tool Registry Discovery
# ═════════════════════════════════════════════════════════════════════════════

class TestToolRegistry:

    def test_registry_contains_expected_types(self):
        from agents.registry import AGENT_REGISTRY
        expected = {"chat", "engineer", "researcher", "server", "daemon"}
        assert expected == set(AGENT_REGISTRY.keys())

    def test_registry_values_are_classes(self):
        from agents.registry import AGENT_REGISTRY
        for key, cls in AGENT_REGISTRY.items():
            assert isinstance(cls, type), f"{key} is not a class"

    def test_registry_classes_inherit_base_agent(self):
        from agents.base_agent import BaseAgent
        from agents.registry import AGENT_REGISTRY
        for key, cls in AGENT_REGISTRY.items():
            assert issubclass(cls, BaseAgent), \
                f"{key} ({cls.__name__}) does not inherit BaseAgent"

    def test_registry_lookup_by_type_string(self):
        from agents.registry import AGENT_REGISTRY
        cls = AGENT_REGISTRY.get("chat")
        assert cls is not None
        assert cls.__name__ == "ChatAgent"

    def test_registry_unknown_type_returns_none(self):
        from agents.registry import AGENT_REGISTRY
        assert AGENT_REGISTRY.get("nonexistent_type") is None


# ═════════════════════════════════════════════════════════════════════════════
# 3. URL Normalizer
# ═════════════════════════════════════════════════════════════════════════════

class TestURLNormalizer:

    def test_lowercases_scheme_and_host(self):
        from daemon.url_parser.normalizer import normalize_url
        result = normalize_url("HTTP://Example.COM/path")
        assert result.startswith("http://example.com")

    def test_removes_default_http_port(self):
        from daemon.url_parser.normalizer import normalize_url
        assert normalize_url("http://example.com:80/page") == "http://example.com/page"

    def test_removes_default_https_port(self):
        from daemon.url_parser.normalizer import normalize_url
        assert normalize_url("https://example.com:443/page") == "https://example.com/page"

    def test_keeps_non_default_port(self):
        from daemon.url_parser.normalizer import normalize_url
        result = normalize_url("http://example.com:8080/page")
        assert "8080" in result

    def test_removes_trailing_slash(self):
        from daemon.url_parser.normalizer import normalize_url
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_preserves_bare_root_slash(self):
        from daemon.url_parser.normalizer import normalize_url
        result = normalize_url("https://example.com/")
        assert result in ("https://example.com/", "https://example.com")

    def test_sorts_query_params(self):
        from daemon.url_parser.normalizer import normalize_url
        a = normalize_url("https://example.com/search?z=last&a=first")
        b = normalize_url("https://example.com/search?a=first&z=last")
        assert a == b

    def test_strips_fragment(self):
        from daemon.url_parser.normalizer import normalize_url
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_collapses_double_slashes_in_path(self):
        from daemon.url_parser.normalizer import normalize_url
        result = normalize_url("https://example.com//double//slash")
        assert "//" not in result.replace("https://", "")

    def test_rejects_non_http_scheme(self):
        from daemon.url_parser.normalizer import normalize_url
        assert normalize_url("ftp://example.com/file") == ""

    def test_rejects_empty_string(self):
        from daemon.url_parser.normalizer import normalize_url
        assert normalize_url("") == ""

    def test_get_root_domain(self):
        from daemon.url_parser.normalizer import get_root_domain
        assert get_root_domain("https://apps.irs.gov/page") == "irs.gov"
        assert get_root_domain("https://www.treasury.gov/") == "treasury.gov"

    def test_is_same_root_domain(self):
        from daemon.url_parser.normalizer import is_same_root_domain
        assert is_same_root_domain("https://apps.irs.gov", "https://www.irs.gov")
        assert not is_same_root_domain("https://irs.gov", "https://treasury.gov")

    def test_strip_query_params(self):
        from daemon.url_parser.normalizer import strip_query_params
        result = strip_query_params("https://example.com/page?foo=bar&baz=1")
        assert result == "https://example.com/page"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Agent Stream Round-Trip
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentStreamRoundTrip:
    """
    Tests BaseAgent.run_stream() without hitting Ollama.
    Patches the underlying run() method so the test is pure-logic only.
    """

    def _make_agent(self, agent_type: str = "chat"):
        from agents.base_agent import BaseAgent
        return BaseAgent(
            name="test-agent",
            type=agent_type,
            provider="ollama",
            model="llama3",
            endpoint="http://localhost:11434",
            timeout_seconds=30,
            temperature=0.0,
            system_prompt="You are a test agent.",
            agent_id=str(uuid.uuid4()),
        )

    def test_run_stream_yields_at_least_one_chunk(self):
        agent = self._make_agent()
        with patch.object(agent, "run", return_value="hello world"):
            chunks = list(agent.run_stream("ping"))
        assert len(chunks) >= 1

    def test_run_stream_output_is_string(self):
        agent = self._make_agent()
        with patch.object(agent, "run", return_value="response text"):
            chunks = list(agent.run_stream("test input"))
        assert all(isinstance(c, str) for c in chunks)

    def test_run_stream_concatenated_output_matches_run(self):
        agent = self._make_agent()
        expected = "the full response"
        with patch.object(agent, "run", return_value=expected):
            chunks = list(agent.run_stream("anything"))
        assert "".join(chunks) == expected

    def test_validate_passes_for_valid_agent(self):
        agent = self._make_agent()
        agent.validate()  # should not raise

    def test_validate_raises_on_missing_name(self):
        agent = self._make_agent()
        agent.name = ""
        with pytest.raises(ValueError, match="name"):
            agent.validate()

    def test_validate_raises_on_bad_temperature(self):
        agent = self._make_agent()
        agent.temperature = 5.0
        with pytest.raises(ValueError, match="temperature"):
            agent.validate()

    def test_validate_raises_on_bad_top_p(self):
        agent = self._make_agent()
        agent.top_p = -0.1
        with pytest.raises(ValueError, match="top_p"):
            agent.validate()

    def test_to_dict_round_trip(self):
        agent = self._make_agent()
        d = agent.to_dict()
        assert d["name"] == "test-agent"
        assert d["type"] == "chat"
        assert d["model"] == "llama3"

    def test_from_dict_dispatches_correct_subclass(self):
        from agents.base_agent import BaseAgent
        from agents.types.chat_agent import ChatAgent
        data = {
            "name": "dispatch-test",
            "type": "chat",
            "provider": "ollama",
            "model": "llama3",
        }
        agent = BaseAgent.from_dict(data)
        assert isinstance(agent, ChatAgent)