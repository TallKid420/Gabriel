"""Memory / knowledge-base REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_memory_service
from api.schemas import (
    MemoryChunk,
    MemoryDeleteRequest,
    MemoryListResponse,
    OkResponse,
)
from api.services.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("", response_model=MemoryListResponse)
def list_memories(svc: MemoryService = Depends(get_memory_service)):
    grouped_raw = svc.list_memories()
    grouped = {
        source: [MemoryChunk(**chunk) for chunk in chunks]
        for source, chunks in grouped_raw.items()
    }
    return MemoryListResponse(count=svc.count(), grouped=grouped)


@router.delete("", response_model=OkResponse)
def delete_memories(
    payload: MemoryDeleteRequest, svc: MemoryService = Depends(get_memory_service)
):
    svc.delete(payload.ids)
    return OkResponse(detail=f"deleted {len(payload.ids)} chunk(s)")
