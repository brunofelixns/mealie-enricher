import json
import logging
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "level": record.levelname.lower(),
            "time": int(record.created * 1000),
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["err"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def configure_logging(level: str) -> None:
    levels = {"trace": 5, "debug": 10, "info": 20, "warn": 30, "error": 40, "fatal": 50}
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(
        level=levels.get(level, logging.INFO) if level != "silent" else logging.CRITICAL + 1,
        handlers=[handler],
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger(__name__).debug("Logger initialized at %s", time.time())
