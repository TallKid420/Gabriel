from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from agents.base_agent import BaseAgent


TOOLS: list[BaseTool] = []


class ServerAgent(BaseAgent):
    def validate(self) -> None:
        super().validate()
        if self.type != "server":
            raise ValueError("ServerAgent must use type 'server'")

    def get_tools(self) -> list[BaseTool]:
        return TOOLS

    def _build_runtime(self) -> ChatOllama:
        return ChatOllama(
            model=self.model,
            base_url=self.endpoint,
            temperature=float(self.temperature),
            top_p=float(self.top_p),
            num_predict=int(self.max_tokens or 1024),
        )

    def run(self, user_input: str) -> str:
        llm = self._build_runtime()
        messages = [HumanMessage(content=user_input)]
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]
        response = llm.invoke(messages)
        return response.content if isinstance(response.content, str) else str(response.content)
