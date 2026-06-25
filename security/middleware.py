from __future__ import annotations

from langchain_core.tools import BaseTool
from security.permission_tool import PermissionWrappedTool


def wrap_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """
    Wrap every tool with the permission gate before passing to create_agent().

        resolved = wrap_tools(self.get_tools())
    """
    return [PermissionWrappedTool(tool) for tool in tools]