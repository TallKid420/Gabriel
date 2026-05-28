import io
import tarfile
import os
import inspect
import docker
from langchain_core.tools import StructuredTool

ALLOWED_IMAGES = [
    "python:3.12-slim",
    "node:20-slim",
    "ubuntu:22.04",
    "gcc:13",
]

WORKSPACE_ROOT = os.environ.get("HERMES_WORKSPACE_ROOT", "/tmp/hermes/workspaces")


class SandboxManager:
    TOOL_METHODS = (
        "create_container",
        "exec_command",
        "copy_to",
        "copy_from",
        "destroy",
    )

    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"[SandboxManager] Docker unavailable: {e}")
            self.client = None

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

    def _get_container(self, project_id: str):
        if not self.client:
            return None
        try:
            return self.client.containers.get(f"workspace-{project_id}")
        except docker.errors.NotFound:
            return None

    def create_container(self, project_id: str, image: str) -> dict:
        """Spin up an isolated Docker container for a Hermes project workspace."""
        if not self.client:
            return {"status": "error", "message": "Docker client not initialized."}
        if image not in ALLOWED_IMAGES:
            return {"status": "error", "message": f"Image not allowed. Allowed: {ALLOWED_IMAGES}"}

        workspace_path = os.path.join(WORKSPACE_ROOT, project_id)
        os.makedirs(workspace_path, exist_ok=True)

        container_name = f"workspace-{project_id}"
        try:
            container = self.client.containers.run(
                image=image,
                name=container_name,
                detach=True,
                tty=True,
                labels={"project_id": project_id, "type": "hermes-sandbox"},
                mem_limit="2g",
                nano_cpus=1_000_000_000,
                network_mode="none",
                volumes={workspace_path: {"bind": "/workspace", "mode": "rw"}},
            )
            return {"status": "created", "container_id": container.short_id, "workspace": workspace_path}
        except docker.errors.Conflict:
            return {"status": "exists", "message": f"{container_name} already running."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def exec_command(self, project_id: str, command: str) -> dict:
        """Run a shell command inside the project container."""
        container = self._get_container(project_id)
        if not container:
            return {"status": "error", "message": f"No container for project {project_id}"}
        try:
            exit_code, output = container.exec_run(
                cmd=["sh", "-c", command],
                workdir="/workspace",
                demux=False,
            )
            return {
                "exit_code": exit_code,
                "output": output.decode("utf-8", errors="replace") if output else "",
                "project_id": project_id,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def copy_to(self, project_id: str, src: str, dest: str) -> dict:
        """Copy a file from the host workspace into the container."""
        container = self._get_container(project_id)
        if not container:
            return {"status": "error", "message": "Container not found."}
        if not os.path.exists(src):
            return {"status": "error", "message": f"Source not found: {src}"}
        try:
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as tar:
                tar.add(src, arcname=os.path.basename(dest))
            stream.seek(0)
            container.put_archive(os.path.dirname(dest) or "/workspace", stream)
            return {"status": "success", "destination": dest}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def copy_from(self, project_id: str, src: str, dest: str) -> dict:
        """Copy a file out of the container to the host."""
        container = self._get_container(project_id)
        if not container:
            return {"status": "error", "message": "Container not found."}
        try:
            bits, stat = container.get_archive(src)
            stream = io.BytesIO()
            for chunk in bits:
                stream.write(chunk)
            stream.seek(0)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with tarfile.open(fileobj=stream, mode="r") as tar:
                tar.extractall(path=os.path.dirname(dest) or ".")
            return {"status": "success", "stat": stat}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def destroy(self, project_id: str) -> dict:
        """Stop and remove the project container."""
        container = self._get_container(project_id)
        if not container:
            return {"status": "not_found", "project_id": project_id}
        try:
            container.stop(timeout=5)
            container.remove(force=True)
            return {"status": "destroyed", "project_id": project_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}