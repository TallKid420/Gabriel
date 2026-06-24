import os
import inspect
import shutil
from pathlib import Path
from langchain_core.tools import StructuredTool

MAX_READ_BYTES = 32_000
MAX_LIST_RESULTS = 200


class WorkspaceManager:
    TOOL_METHODS = (
        "create",
        "write_file",
        "read_file",
        "list_files",
        "save_artifact",
        "destroy",
    )

    def __init__(self):
        self.base_path = Path(
            os.environ.get("HERMES_WORKSPACE_ROOT", "/var/lib/hermes/projects")
        )
        self.tools = self._build_tools()

    def _build_tools(self):
        built = []
        for name in self.TOOL_METHODS:
            method = getattr(self, name)
            built.append(
                StructuredTool.from_function(
                    func=method,
                    name=name,
                    description=inspect.getdoc(method) or name,
                )
            )
        return built

    def get_tools(self, *names: str):
        if not names:
            return self.tools
        wanted = set(names)
        return [tool for tool in self.tools if tool.name in wanted]

    def _get_path(self, project_id: str, *subpaths: str) -> Path:
        """Resolve a path and assert it stays within the project workspace."""
        project_root = (self.base_path / project_id).resolve()

        if not project_root.is_relative_to(self.base_path.resolve()):
            raise ValueError("Invalid project_id: escapes base path.")

        if not subpaths:
            return project_root

        candidate = (project_root / Path(*subpaths)).resolve()

        if not candidate.is_relative_to(project_root):
            raise ValueError(f"Path traversal detected: {subpaths!r} escapes project workspace.")

        return candidate

    def create(self, project_id: str) -> dict:
        """Create the workspace directory for a project. Returns the path."""
        path = self._get_path(project_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "artifacts").mkdir(exist_ok=True)
        (path / "src").mkdir(exist_ok=True)
        return {"status": "created", "path": str(path)}

    def write_file(self, project_id: str, path: str, content: str) -> dict:
        """Write a file into the project workspace at the given relative path."""
        try:
            full_path = self._get_path(project_id, path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return {"status": "success", "path": str(full_path.relative_to(self.base_path))}
        except ValueError as e:
            return {"status": "error", "message": str(e)}

    def read_file(self, project_id: str, path: str) -> dict:
        """Read a file from the project workspace. Returns content up to 32KB."""
        try:
            full_path = self._get_path(project_id, path)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if not full_path.exists():
            return {"status": "error", "message": f"File not found: {path}"}

        size = full_path.stat().st_size
        if size > MAX_READ_BYTES:
            return {
                "status": "truncated",
                "message": f"File is {size} bytes, limit is {MAX_READ_BYTES}.",
                "content": full_path.read_text(encoding='utf-8', errors='replace')[:MAX_READ_BYTES],
            }

        return {
            "status": "success",
            "content": full_path.read_text(encoding="utf-8", errors="replace"),
        }

    def list_files(self, project_id: str, subpath: str = ".") -> dict:
        """List files in the project workspace, optionally scoped to a subdirectory."""
        try:
            root = self._get_path(project_id, subpath)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if not root.exists():
            return {"status": "error", "message": f"Path not found: {subpath}"}

        files = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file()
        ]

        return {
            "status": "success",
            "files": files[:MAX_LIST_RESULTS],
            "truncated": len(files) > MAX_LIST_RESULTS,
            "total": len(files),
        }

    def save_artifact(self, project_id: str, src_relative_path: str, kind: str) -> dict:
        """
        Promote a file already in the workspace to the artifacts directory.
        src_relative_path must be relative to the project workspace root.
        """
        try:
            src = self._get_path(project_id, src_relative_path)
            artifact_dir = self._get_path(project_id, "artifacts", kind)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if not src.exists():
            return {"status": "error", "message": f"Source not found: {src_relative_path}"}

        artifact_dir.mkdir(parents=True, exist_ok=True)
        dest = artifact_dir / src.name
        shutil.copy2(src, dest)
        return {"status": "saved", "destination": str(dest.relative_to(self.base_path))}

    def destroy(self, project_id: str) -> dict:
        """Permanently delete the project workspace and all its contents."""
        try:
            path = self._get_path(project_id)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        if path.exists():
            shutil.rmtree(path)
        return {"status": "destroyed", "project_id": project_id}