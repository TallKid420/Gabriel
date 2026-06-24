from __future__ import annotations

from agents.types.chat_agent import ChatAgent
# from agents.server_agent import ServerAgent
# from agents.types.daemon_agent import DaemonAgent
# from agents.types.engineer_agent import EngineerAgent
# from agents.types.researcher_agent import ResearcherAgent


AGENT_REGISTRY = {
    "chat": ChatAgent,
    # "engineer": EngineerAgent,
    # "researcher": ResearcherAgent,
    # "server": ServerAgent,
    # "daemon": DaemonAgent,
}
