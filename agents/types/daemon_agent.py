from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama

from agents.base_agent import BaseAgent


TOOLS: list[BaseTool] = []


class DaemonAgent(BaseAgent):
    def validate(self) -> None:
        super().validate()
        if self.type != "daemon":
            raise ValueError("DaemonAgent must use type 'daemon'")

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

    def run_stream(self, user_input: str):
        llm = self._build_runtime()
        messages = [HumanMessage(content=user_input)]
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]
        for chunk in llm.stream(messages):
            content = getattr(chunk, "content", "")
            if isinstance(content, str):
                if content:
                    yield content
            elif content:
                yield str(content)
