from pathlib import Path

from config.config_loader import (
    load_tool_config,
    ToolConfig
)


class ToolConfigManager:

    def __init__(
        self,
        config_path="config/tool_config.yaml"
    ):

        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(
                self.config_path
            )

        self.tools: ToolConfig | None = None

        self.load()


    def load(self):

        self.tools = load_tool_config(
            self.config_path
        )


    def reload(self):

        self.load()


    def get_files(self):
        if self.tools is None:
            raise RuntimeError("Tool configuration has not been loaded")

        return self.tools.files


    def get_email(self):
        if self.tools is None:
            raise RuntimeError("Tool configuration has not been loaded")

        return self.tools.email


    def get_calendar(self):
        if self.tools is None:
            raise RuntimeError("Tool configuration has not been loaded")

        return self.tools.calendar