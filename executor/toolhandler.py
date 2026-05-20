from langchain_core.callbacks import BaseCallbackHandler
import logging

log = logging.getLogger(__name__)

class ToolLogger(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        log.info(f"\n[TOOL CALL]\nname: {serialized.get('name')}\nargs: {input_str}")

    def on_tool_end(self, output, **kwargs):
        log.info(f"\n[TOOL RESULT]\n{output}")