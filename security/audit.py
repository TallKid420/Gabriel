from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

AUDIT_FILE = Path("audit.jsonl")


class AuditLogger:
    def write(self, **fields) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **fields}
        try:
            with AUDIT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            log.warning("Audit write failed: %s", exc)


audit = AuditLogger()