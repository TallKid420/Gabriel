from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import agents, chat, memory, sessions, tools
from api.routes.permissions import router as permissions_router
from api.websocket import router as ws_router

app = FastAPI(
    title="Gabriel API",
    version="1.0.0",
    description="Backend for the Gabriel agent platform"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(tools.router)
app.include_router(memory.router)
app.include_router(permissions_router)
app.include_router(ws_router)