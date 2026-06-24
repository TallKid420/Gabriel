"""Agent catalog REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_config_service
from api.schemas import (
    AgentCreate,
    AgentListResponse,
    AgentSummary,
    AgentUpdate,
    OkResponse,
)
from api.services.config_service import ConfigService

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
def list_agents(
    enabled_only: bool = False, config: ConfigService = Depends(get_config_service)
):
    agents = config.list_enabled_agents() if enabled_only else config.list_agents()
    return AgentListResponse(
        agents=[AgentSummary(**config.agent_to_summary(a)) for a in agents]
    )


@router.get("/{name}", response_model=AgentSummary)
def get_agent(name: str, config: ConfigService = Depends(get_config_service)):
    agent = config.get_agent(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return AgentSummary(**config.agent_to_summary(agent))


@router.post("", response_model=AgentSummary, status_code=201)
def create_agent(
    payload: AgentCreate, config: ConfigService = Depends(get_config_service)
):
    try:
        agent = config.add_agent(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return AgentSummary(**config.agent_to_summary(agent))


@router.patch("/{name}", response_model=OkResponse)
def update_agent(
    name: str, payload: AgentUpdate, config: ConfigService = Depends(get_config_service)
):
    try:
        ok = config.update_agent(name, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return OkResponse(detail="updated")


@router.delete("/{name}", response_model=OkResponse)
def delete_agent(name: str, config: ConfigService = Depends(get_config_service)):
    if not config.remove_agent(name):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return OkResponse(detail="deleted")


@router.post("/{name}/enable", response_model=OkResponse)
def enable_agent(name: str, config: ConfigService = Depends(get_config_service)):
    if not config.enable_agent(name):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return OkResponse(detail="enabled")


@router.post("/{name}/disable", response_model=OkResponse)
def disable_agent(name: str, config: ConfigService = Depends(get_config_service)):
    if not config.disable_agent(name):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return OkResponse(detail="disabled")
