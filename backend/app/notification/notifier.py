"""Notifier — dispatches alerts when the rule engine confirms a violation.

Channel(s) are TBD; this stub logs to stdout until a real channel is wired up.
"""

import structlog

logger = structlog.get_logger(__name__)


class Notifier:
    def send(self, message: str, evidence_path: str | None = None) -> None:
        """Send a compliance violation alert."""
        logger.warning("violation_alert", message=message, evidence_path=evidence_path)
