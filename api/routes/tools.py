"""Tool discovery + per-agent enablement REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_config_service, get_tool_service
from api.schemas import (
    AgentToolStates,
    OkResponse,
    ToolListResponse,
    ToolSummary,
    ToolToggleRequest,
)
from api.services.config_service import ConfigService
from api.services.tool_service import ToolService

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=ToolListResponse)
def list_tools(svc: ToolService = Depends(get_tool_service)):
    return ToolListResponse(tools=[ToolSummary(**t) for t in svc.list_tools()])


@router.get("/agents")
def list_tool_agents(
    svc: ToolService = Depends(get_tool_service),
    config: ConfigService = Depends(get_config_service),
):
    """Sync the config agent catalog into the tool DB and return agent identities."""
    config_agents = config.list_agents()
    if config_agents:
        svc.sync_agents([(a.agent_id, a.name) for a in config_agents])
    return {"agents": svc.list_agents()}


@router.get("/agents/{agent_id}/states", response_model=AgentToolStates)
def get_agent_tool_states(agent_id: str, svc: ToolService = Depends(get_tool_service)):
    svc.sync_agent_tools(agent_id)
    return AgentToolStates(agent_id=agent_id, states=svc.get_agent_tool_states(agent_id))


@router.post("/toggle", response_model=OkResponse)
def toggle_tool(payload: ToolToggleRequest, svc: ToolService = Depends(get_tool_service)):
    svc.set_tool_enabled(payload.agent_id, payload.tool_id, payload.enabled)
    return OkResponse(detail="updated")
