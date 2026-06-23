from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core._api.beta_decorator import LangChainBetaWarning
from langgraph.checkpoint.sqlite import SqliteSaver

from executor.toolhandler import load_tool_registry
from agents.base_agent import BaseAgent
from daemon.database import Database

import warnings
import logging

log = logging.getLogger(__name__)

class DaemonAgent(BaseAgent):
    def validate(self) -> None:
        super().validate()
        if self.type != "daemon":
            raise ValueError("DaemonAgent must use type 'daemon'")
        
        warnings.filterwarnings(
            "ignore",
            category=LangChainBetaWarning
        )

        self.db = Database()
        self._registry = load_tool_registry()
        self.db.sync_agent_tools(self.agent_id, self._registry.tool_ids())
        self._enabled_tool_ids = self.db.get_enabled_tool_ids(self.agent_id)
        self.agent = self._build_runtime()

    def get_tools(self) -> list[BaseTool]:
        return self._registry.resolve_enabled(self._enabled_tool_ids)

    def _build_runtime(self):
        
        # Build Agent Config

        self.llm = ChatOllama(
            model=self.model,
            base_url=self.endpoint,
            temperature=float(self.temperature),
            top_p=float(self.top_p),
            max_tokens=int(self.max_tokens or 1024),
        )

        memory = Database().connect_sync()

        return create_agent(
            model=self.llm,
            tools=self.get_tools(),
            system_prompt=self.system_prompt,
            checkpointer=SqliteSaver(memory),
        )
    
    def run(self, user_input: str, thread_id: str) -> str:
        response = self.agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        return response["messages"][-1].content

    def run_stream(self, user_input: str, thread_id: str):

        stream = self.agent.stream_events(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
            version="v3",
        )

        tool_end = False
        for name, item in stream.interleave("messages", "tool_calls"):

            if name == "messages":
                if tool_end:
                    tool_end = False
                    continue
                for delta in item.text:
                    yield {
                        "type": "text",
                        "content": delta,
                    }

            elif name == "tool_calls":

                yield {
                    "type": "tool_start",
                    "name": item.tool_name,
                    "input": item.input,
                }

                for delta in item.output_deltas:
                    yield {
                        "type": "tool_output",
                        "name": item.tool_name,
                        "content": delta,
                    }

                tool_end = True
                yield {
                    "type": "tool_end",
                    "name": item.tool_name,
                    "output": item.output,
                    "error": item.error,
                }
