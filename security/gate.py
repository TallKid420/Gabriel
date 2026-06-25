from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class PendingApproval:
    request_id: str
    tool_id: str
    category: str
    arguments: dict
    event: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


class ApprovalGate:
    """
    Thread-safe store for in-flight permission requests.

    The producer thread (agent stream) calls wait_for_approval() and blocks.
    The FastAPI route handler calls resolve() when the user responds.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict[str, PendingApproval] = {}

    def create(self, tool_id: str, category: str, arguments: dict) -> PendingApproval:
        request_id = str(uuid.uuid4())
        approval = PendingApproval(
            request_id=request_id,
            tool_id=tool_id,
            category=category,
            arguments=arguments,
        )
        with self._lock:
            self._pending[request_id] = approval
        return approval

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Called by the REST endpoint. Returns False if request_id not found."""
        with self._lock:
            approval = self._pending.get(request_id)
        if approval is None:
            return False
        approval.approved = approved
        approval.event.set()
        return True

    def wait_for_approval(self, approval: PendingApproval, timeout: float = 120.0) -> bool:
        """Block the calling thread until the user responds or timeout."""
        fired = approval.event.wait(timeout=timeout)
        with self._lock:
            self._pending.pop(approval.request_id, None)
        if not fired:
            return False  # timeout → treat as denial
        return approval.approved


# Process-wide singleton
approval_gate = ApprovalGate()