"""Log formatters — JSON and human-readable output."""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "entity_type": getattr(record, "entity_type", "system"),
            "entity_id": getattr(record, "entity_id", ""),
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add payload if present
        payload = getattr(record, "payload", None)
        if payload:
            log_entry["payload"] = payload

        # Add exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter for console output."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        entity_type = getattr(record, "entity_type", "")
        entity_id = getattr(record, "entity_id", "")

        entity = ""
        if entity_type:
            entity = f" [{entity_type}"
            if entity_id:
                entity += f":{entity_id}"
            entity += "]"

        msg = f"{ts} {record.levelname:<8}{entity} {record.getMessage()}"

        if record.exc_info and record.exc_info[1]:
            msg += "\n" + self.formatException(record.exc_info)

        return msg
