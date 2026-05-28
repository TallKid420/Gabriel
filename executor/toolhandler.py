import ast
import importlib.util
import logging
import re
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger(__name__)


class ToolLogger(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        log.info(f"\n[TOOL CALL]\nname: {serialized.get('name')}\nargs: {input_str}")

    def on_tool_end(self, output, **kwargs):
        log.info(f"\n[TOOL RESULT]\n{output}")


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


def _load_tools_from_folder(folder_name: str) -> list:
    normalized = (folder_name or "").strip().lower()
    if not normalized or not re.fullmatch(r"[a-z0-9_-]+", normalized):
        return []

    root = Path(__file__).resolve().parent / "tools"
    target = root / normalized
    if not target.exists() or not target.is_dir():
        return []

    loaded = []
    for script_path in sorted(target.glob("*.py")):
        if script_path.name == "__init__.py":
            continue
        module_name = f"executor.tools.{normalized}.{script_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in vars(module).values():
                if hasattr(value, "name") and hasattr(value, "invoke"):
                    loaded.append(value)
        except Exception:
            continue
    return loaded


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
                functions.append({"name": node.name, "tool_decorated": _is_tool_decorated(node)})

        discovered.append({"script": script_path.name, "functions": functions})

    flat = []
    for entry in discovered:
        script = entry.get("script", "")
        for fn in entry.get("functions", []):
            if fn.get("tool_decorated"):
                flat.append({"name": fn["name"], "script": script})

    return {
        "folder": normalized,
        "count": len(flat),
        "tools": flat,
        "scripts": discovered,
    }


def build_tool_list(folder_name: str) -> list:
    return _load_tools_from_folder(folder_name)
