from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from app.core.request_subject import get_request_subject

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get()
        uid, subject_src = get_request_subject()
        if not hasattr(record, "subject_user_id"):
            record.subject_user_id = "-" if uid is None else str(uid)
        if not hasattr(record, "subject_source"):
            record.subject_source = subject_src
        return True


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    fmt = (
        "%(asctime)s | %(levelname)-5s | %(request_id)s | %(subject_user_id)s@%(subject_source)s | "
        "%(name)s | %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        logging.getLogger(name).setLevel(log_level)

    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False

    logging.getLogger("app").setLevel(log_level)
