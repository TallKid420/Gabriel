from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"
    ASK   = "ask"
    DENY  = "deny"


@dataclass
class PermissionRequest:
    tool_id:   str
    category:  str
    tool_name: str
    arguments: dict


# Edit this dict to tighten or loosen per-category rules.
_DEFAULT_POLICY: dict[str, Decision] = {
    "calendar":   Decision.ASK,
    "database":   Decision.ASK,
    "system":     Decision.ASK,
    "shell":      Decision.DENY,
    "network":    Decision.ASK,
    "email":      Decision.ASK,
    "git":        Decision.ASK,
    "search":     Decision.ALLOW,
    "memory":     Decision.ALLOW,
}


class PermissionManager:
    def __init__(self, policy: dict[str, Decision] | None = None):
        self._policy = policy or _DEFAULT_POLICY

    def check(self, request: PermissionRequest) -> Decision:
        return self._policy.get(request.category, Decision.ALLOW)


# Singleton used across the security package
permission_manager = PermissionManager()