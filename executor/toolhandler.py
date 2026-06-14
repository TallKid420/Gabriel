from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import BaseTool

import ast
import importlib.util
import logging
import re

log = logging.getLogger(__name__)


class ToolLogger(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        log.info(f"\n[TOOL CALL]\nname: {serialized.get('name')}\nargs: {input_str}")

    def on_tool_end(self, output, **kwargs):
        log.info(f"\n[TOOL RESULT]\n{output}")

@dataclass
class ToolRecord:
    id: str
    display_name: str
    category: str
    callable: BaseTool
    description: str = ""
    enabled: bool = False

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolRecord] = {}

    def register(self, record: ToolRecord) -> None:
        if record.id in self._tools:
            raise ValueError(f"Duplicate tool ID: '{record.id}'")
        self._tools[record.id] = record

    def get(self, tool_id: str) -> ToolRecord:
        return self._tools.get(tool_id)
    
    def list_tools(self) -> List[ToolRecord]:
        return list(self._tools.values())

    def resolve_for_agent(self, tool_ids: List[str]) -> list[BaseTool]:
        resolved = []
        for tool_id in tool_ids:
            record = self._tools.get(tool_id)
            if record is None:
                log.warning(f"Tool ID not found in registry: {tool_id}")
                continue
            if not record.enabled:
                log.debug(f"Tool disabled, skipping: {tool_id}")
                continue
            resolved.append(record.callable)
        return resolved

    def requires_approval(self, tool_id: str):
        record = self._tools.get(tool_id)
        return record.requires_approval if record else False

    def get_enabled_tools(self) -> list[BaseTool]:
        return [record.callable for record in self._tools.values() if record.enabled]


def load_tool_registry(enabled_ids: Optional[set[str]] = None) -> ToolRegistry:
    registry = ToolRegistry()
    root = Path(__file__).resolve().parent / "tools"

    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        category = folder.name

        for script_path in sorted(folder.glob("*.py")):
            if script_path.name == "__init__.py":
                continue

            module_name = f"executor.tools.{category}.{script_path.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, script_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as exc:
                log.warning(f"Failed to load tool module {script_path}: {exc}")
                continue

            for value in vars(module).values():
                if not (hasattr(value, "name") and hasattr(value, "invoke")):
                    continue

                tool_id = f"{category}.{value.name}"
                display_name = str(value.name).replace("_", " ").title()
                description = getattr(value, "description", "") or ""


                #TODO if broken use: enabled = tool_id in enabled_ids if enabled_ids is not None else True
                enabled = {
                    tool_id in enabled_ids
                    if enabled_ids is not None
                    else True
                }
                
                record = ToolRecord(
                    id=tool_id,
                    display_name=display_name,
                    category=category,
                    description=description,
                    callable=value,
                    enabled=enabled,
                )

                registry.register(record)
                
    return registry


def discover_tools_by_folder(folder_name: str) -> dict:
    normalized = (folder_name or "").strip().lower()
    if not normalized:
        return {"error": "folder_name is required"}
    if not re.fullmatch(r"[a-z0-9_-]+", normalized):
        return {"error": "folder_name must only contain letters, numbers, underscore, or hyphen"}

    root = Path(__file__).resolve().parent / "tools"
    target = root / normalized
    if not target.exists() or not target.is_dir():
        return {"folder": normalized, "count": 0, "tools": [], "error": f"Tool folder '{normalized}' not found"}

    discovered = []
    for script_path in sorted(target.glob("*.py")):
        if script_path.name == "__init__.py":
            continue
        try:
            module_ast = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
        except Exception as exc:
            discovered.append({"script": script_path.name, "functions": [], "error": str(exc)})
            continue

        functions = []
        for node in module_ast.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                is_tool = _is_tool_decorated(node)
                functions.append({"name": node.name, "tool_decorated": is_tool})

        discovered.append({"script": script_path.name, "functions": functions})

    flat = [
        {"name": fn["name"], "script": entry.get("script", "")}
        for entry in discovered
        for fn in entry.get("functions", [])
        if fn.get("tool_decorated")
    ]

    return {"folder": normalized, "count": len(flat), "tools": flat, "scripts": discovered}


def _is_tool_decorated(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "tool":
            return True
        if isinstance(decorator, ast.Call):
            fn = decorator.func
            if isinstance(fn, ast.Name) and fn.id == "tool":
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == "tool":
                return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
            return True
    return False
