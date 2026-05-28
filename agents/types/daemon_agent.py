from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core._api.beta_decorator import LangChainBetaWarning
from langgraph.checkpoint.memory import InMemorySaver

from agents.base_agent import BaseAgent
from executor.toolhandler import build_tool_list

import warnings


TOOLS: list[BaseTool] = []


class DaemonAgent(BaseAgent):
    def validate(self) -> None:
        super().validate()
        if self.type != "daemon":
            raise ValueError("DaemonAgent must use type 'daemon'")
        
        warnings.filterwarnings(
            "ignore",
            category=LangChainBetaWarning
        )

        self.agent = self._build_runtime()

    def get_tools(self) -> list[BaseTool]:
        return TOOLS

    def _build_runtime(self):
        
        # Build Agent Config

        self.llm = ChatOllama(
            model=self.model,
            base_url=self.endpoint,
            temperature=float(self.temperature),
            top_p=float(self.top_p),
            max_tokens=int(self.max_tokens or 1024),
        )

        return create_agent(
            model=self.llm,
            tools=self.get_tools(),
            system_prompt=self.system_prompt,
            checkpointer=InMemorySaver(),
        )

    def run(self, user_input: str, thread_id: str) -> str:
        response = self.agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        return response["messages"][-1].content

    def run_stream(self, user_input: str):

        stream = self.agent.stream_events(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": "1"}},
            version="v3",
        )

        tool_end = False
        for name, item in stream.interleave("messages", "tool_calls"):

            if name == "messages":
                if tool_end:
                    print(f"Received tool message: {item.text}")
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
