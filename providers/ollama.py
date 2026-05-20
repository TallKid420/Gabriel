from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


class OllamaBackend:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        return self.model_manager.list_models()

    def _to_langchain_messages(
        self,
        messages: list[dict[str, str]],
        enabled_skills: dict[str, bool],
    ) -> list[SystemMessage | HumanMessage | AIMessage]:
        skills_text = "\n".join([f"- {key}: {'enabled' if val else 'disabled'}" for key, val in enabled_skills.items()])
        skill_message = SystemMessage(content=f"Skills:\n{skills_text}")
        langchain_messages: list[SystemMessage | HumanMessage | AIMessage] = [skill_message]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))
        return langchain_messages

    @staticmethod
    def build_runtime(
            model: str, 
            endpoint: str, 
            temperature: float, 
            top_p: Optional[float] = None,
            max_tokens: Optional[int] = None
        ):
        return ChatOllama(
            model=model,
            base_url=endpoint,
            temperature=temperature,
            top_p=top_p,
            num_predict=max_tokens,
        )