"""
Permission approval endpoint.

The Streamlit frontend POSTs here when the user clicks Allow or Deny.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from security.gate import approval_gate

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


class PermissionResponse(BaseModel):
    approved: bool


@router.post("/{request_id}/respond")
def respond(request_id: str, body: PermissionResponse):
    ok = approval_gate.resolve(request_id, body.approved)
    if not ok:
        raise HTTPException(status_code=404, detail="Permission request not found or already resolved")
    return {"status": "ok", "approved": body.approved}