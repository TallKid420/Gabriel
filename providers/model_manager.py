from __future__ import annotations

from providers.ollama import OllamaBackend
from agents.base_agent import BaseAgent
from pathlib import Path
from typing import Optional

import os
import yaml


class ModelManager:

    def build_runtime(
            self, 
            provider: str,
            model: str, 
            endpoint: str, 
            temperature: float, 
            top_p: Optional[float] = None,
            max_tokens: Optional[int] = None
        ):
        match provider:
            case "ollama":
                OllamaBackend.build_runtime(
                    model=model,
                    endpoint=endpoint,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens
                )
            case "_":
                raise ValueError(f"Invalid Provider: {provider}")

#     def _default_config(self) -> dict[str, Any]:
#         default_endpoint = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
#         default_model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
#         return {
#             "default_profile": "default",
#             "profiles": {
#                 "default": {
#                     "provider": "ollama",
#                     "endpoint": default_endpoint,
#                     "model": default_model,
#                     "temperature": 0.3,
#                     "top_p": 0.95,
#                     "max_tokens": 1024,
#                     "context_window": 4096,
#                     "options": {},
#                 }
#             },
#         }

#     def _load_config(self) -> dict[str, Any]:
#         if not self.config_path.exists():
#             return self._default_config()
#         with self.config_path.open("r", encoding="utf-8") as file:
#             loaded = yaml.safe_load(file) or {}
#         if not isinstance(loaded, dict):
#             return self._default_config()
#         profiles = loaded.get("profiles")
#         if not isinstance(profiles, dict) or not profiles:
#             return self._default_config()
#         default_profile = str(loaded.get("default_profile", "default"))
#         if default_profile not in profiles:
#             default_profile = next(iter(profiles.keys()))
#         return {"default_profile": default_profile, "profiles": profiles}

#     def default_profile(self) -> str:
#         profiles = self._config.get("profiles", {})
#         if not isinstance(profiles, dict) or not profiles:
#             return "default"
#         configured = str(self._config.get("default_profile", "")).strip()
#         if configured and configured in profiles:
#             return configured
#         return next(iter(profiles.keys()))

#     def default_model(self) -> str:
#         profile = self.resolve_model_config(self.default_profile())
#         return str(profile.get("model", "gpt-oss:20b"))

#     def list_models(self) -> list[str]:
#         profiles = self._config.get("profiles", {})
#         if not isinstance(profiles, dict) or not profiles:
#             return [self.default_model()]
#         values = [str(v.get("model", "")).strip() for v in profiles.values() if isinstance(v, dict)]
#         models = [value for value in values if value]
#         return models or [self.default_model()]

#     def get_model_config(self, model_name: str) -> dict[str, Any]:
#         return self.resolve_model_config(model_name)

#     def resolve_model_config(self, selection: str) -> dict[str, Any]:
#         profiles = self._config.get("profiles", {})
#         if not isinstance(profiles, dict):
#             profiles = {}
#         base = profiles.get(self.default_profile(), {})
#         selected_profile_name = ""
#         selected_profile: dict[str, Any] = {}

#         if selection in profiles and isinstance(profiles[selection], dict):
#             selected_profile_name = selection
#             selected_profile = profiles[selection]
#         else:
#             for profile_name, profile in profiles.items():
#                 if isinstance(profile, dict) and str(profile.get("model", "")) == selection:
#                     selected_profile_name = profile_name
#                     selected_profile = profile
#                     break

#         if not selected_profile:
#             selected_profile_name = "adhoc"
#             selected_profile = {
#                 "provider": str(base.get("provider")),
#                 "endpoint": str(base.get("endpoint")),
#                 "model": selection or str(base.get("model")),
#                 "temperature": base.get("temperature"),
#                 "top_p": base.get("top_p"),
#                 "max_tokens": base.get("max_tokens"),
#                 "context_window": base.get("context_window"),
#                 "options": base.get("options"),
#             }

#         merged = {
#             "provider": selected_profile.get("provider", base.get("provider")),
#             "endpoint": selected_profile.get("endpoint", base.get("endpoint")),
#             "model": selected_profile.get("model", base.get("model")),
#             "temperature": selected_profile.get("temperature", base.get("temperature")),
#             "top_p": selected_profile.get("top_p", base.get("top_p")),
#             "max_tokens": selected_profile.get("max_tokens", base.get("max_tokens")),
#             "context_window": selected_profile.get("context_window", base.get("context_window")),
#             "options": selected_profile.get("options", base.get("options", {})),
#             "metadata": selected_profile.get("metadata", {}),
#             "profile": selected_profile_name,
#         }

#         if not merged["endpoint"]:
#             merged["endpoint"] = os.getenv("OLLAMA_BASE_URL")

#         return merged

    # def _build_runtime():
