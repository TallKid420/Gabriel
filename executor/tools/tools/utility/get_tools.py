import inspect

import hermes.executor as executor_package
from executor.toolhandler import discover_tools_by_folder
from langchain_core.tools import tool



@tool(
    "get_tools",
    description="Return available tool names/descriptions, or tools discovered in a specific tool folder.",
    return_direct=False,
)
def get_tools(folder_name: str = ""):
    """Return tool metadata.

    Args:
        folder_name: Optional tool folder name under executor/tools (for example: system, text, time).
    """
    if folder_name:
        return discover_tools_by_folder(folder_name)

    tools = []
    for name, fn in getattr(executor_package, "EXECUTOR", {}).items():
        if not callable(fn) or name.startswith("_"):
            continue
        description = inspect.getdoc(fn) or ""
        tools.append({"name": name, "description": description.strip().split("Args:", 1)[0].strip()})
    return {"count": len(tools), "tools": tools}
