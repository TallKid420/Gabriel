"""Memory / knowledge-base REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pathlib import Path

from api.services.memory_service import MemoryService
from api.dependencies import get_memory_service
from api.schemas import (
    MemoryChunk,
    MemoryDeleteRequest,
    MemoryListResponse,
    IngestURL,
    IngestFile,
    OkResponse,
)

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
def delete_memories(payload: MemoryDeleteRequest, svc: MemoryService = Depends(get_memory_service)):
    svc.delete(payload.ids)
    return OkResponse(detail=f"deleted {len(payload.ids)} chunk(s)")


@router.post("/url", response_model=OkResponse)
async def ingest_url(payload: IngestURL, svc: MemoryService = Depends(get_memory_service)):
    if payload.url:
        await svc.ingest_url(payload.url)
        return OkResponse(detail=f"Ingested URL: {payload.url}")
    else:
        raise HTTPException(status_code=400, detail="No resource to ingest")
    
@router.post("/file", response_model=OkResponse)
async def ingest_file(payload: IngestFile, svc: MemoryService = Depends(get_memory_service)):
    if payload.file:
        # FIXME add real upload location
        # Resolve save directory. Do not hardcode, uvicorn can change where it points
        upload_dir = Path(__file__).resolve().parents[2] / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / payload.file.filename

        data = await payload.file.read()

        destination.write_bytes(data)
        await svc.ingest_file(destination.as_posix())

        return OkResponse(detail=f"Ingested File: {payload.file.filename}")
    else:
        raise HTTPException(status_code=400, detail="No resource to ingest")