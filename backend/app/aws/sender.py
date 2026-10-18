"""The sender Lambda: EventBridge Scheduler calls it every 15 minutes; each call
sends at most one queued email (see worker.process_queue)."""

import logging
from dataclasses import asdict
from typing import Any

from app.aws import ssm

ssm.load_into_environment()  # before the worker reads the config

from app import worker  # noqa: E402

log = logging.getLogger("app.sender")
log.setLevel(logging.INFO)


def handler(event: Any, context: Any) -> dict[str, Any]:
    result = worker.process_queue()
    log.info("%s: %s", result.outcome, result.detail)
    return asdict(result)
