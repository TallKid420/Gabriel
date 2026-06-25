from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool

from security.audit import audit
from security.gate import approval_gate
from security.permissions import Decision, PermissionRequest, permission_manager

log = logging.getLogger(__name__)

# Injected by the stream normalizer so the tool can emit a permission_request
# event into the SSE stream before blocking.
_event_callback: Any = None


def set_event_callback(cb) -> None:
    global _event_callback
    _event_callback = cb


def _emit(event: dict) -> None:
    if callable(_event_callback):
        try:
            _event_callback(event)
        except Exception:
            pass


class PermissionWrappedTool(BaseTool):
    """
    Wraps any BaseTool with a permission gate + audit log.

    ALLOW → runs immediately.
    ASK   → emits a permission_request SSE event, blocks until the user
            responds via POST /api/permissions/{request_id}/respond,
            then either runs the tool or returns a denial string.
    DENY  → returns a denial string immediately, never runs the tool.
    """

    name: str = ""
    description: str = ""

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, tool: BaseTool, **kwargs):
        super().__init__(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            **kwargs,
        )
        object.__setattr__(self, "_wrapped_tool", tool)

    def _run(self, *args, **kwargs) -> Any:
        tool: BaseTool = object.__getattribute__(self, "_wrapped_tool")
        category = tool.name.split(".")[0] if "." in tool.name else "unknown"

        request = PermissionRequest(
            tool_id=tool.name,
            category=category,
            tool_name=tool.name,
            arguments=kwargs,
        )
        decision = permission_manager.check(request)

        # ── DENY ──────────────────────────────────────────────────────────────
        if decision == Decision.DENY:
            audit.write(tool=tool.name, category=category,
                        decision="denied", arguments=kwargs, reason="policy_deny")
            return f'Tool "{tool.name}" is not permitted by policy.'

        # ── ALLOW ─────────────────────────────────────────────────────────────
        if decision == Decision.ALLOW:
            audit.write(tool=tool.name, category=category,
                        decision="allowed", arguments=kwargs)
            return self._execute(tool, kwargs)

        # ── ASK ───────────────────────────────────────────────────────────────
        approval = approval_gate.create(
            tool_id=tool.name,
            category=category,
            arguments=kwargs,
        )
        audit.write(tool=tool.name, category=category,
                    decision="pending", arguments=kwargs,
                    request_id=approval.request_id)

        # Emit the event into the SSE stream so the frontend can show the dialog
        _emit({
            "type":       "permission_request",
            "request_id": approval.request_id,
            "tool":       tool.name,
            "category":   category,
            "arguments":  kwargs,
        })

        # Block this thread until the user responds (or timeout)
        approved = approval_gate.wait_for_approval(approval)

        if approved:
            audit.write(tool=tool.name, category=category,
                        decision="approved_by_user", arguments=kwargs,
                        request_id=approval.request_id)
            return self._execute(tool, kwargs)
        else:
            audit.write(tool=tool.name, category=category,
                        decision="denied_by_user", arguments=kwargs,
                        request_id=approval.request_id)
            return "Tool execution denied by user."

    @staticmethod
    def _execute(tool: BaseTool, kwargs: dict) -> Any:
        try:
            result = tool.invoke(kwargs)
            audit.write(tool=tool.name, result="success")
            return result
        except Exception as exc:
            audit.write(tool=tool.name, result="failed", error=str(exc))
            raise