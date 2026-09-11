"""Database persistence metrics — thread-safe counters."""
from __future__ import annotations

import threading


class DatabaseMetrics:
    """Counters for database write operations.

    All increments are thread-safe (GIL + simple int arithmetic).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.write_failures: int = 0
        self.transaction_rollbacks: int = 0
        self.frames_persisted: int = 0
        self.detections_persisted: int = 0
        self.observations_persisted: int = 0
        self.state_transitions_persisted: int = 0
        self.compliance_evaluations_persisted: int = 0
        self.violations_persisted: int = 0
        self.evidence_items_persisted: int = 0
        self.audit_events_persisted: int = 0
        self.pending_events: int = 0

    # ── Increment helpers ─────────────────────────────────────────────────────

    def record_write_failure(self) -> None:
        with self._lock:
            self.write_failures += 1

    def record_rollback(self) -> None:
        with self._lock:
            self.transaction_rollbacks += 1

    def record_violation(self) -> None:
        with self._lock:
            self.violations_persisted += 1

    def record_evidence_item(self) -> None:
        with self._lock:
            self.evidence_items_persisted += 1

    def record_audit_event(self) -> None:
        with self._lock:
            self.audit_events_persisted += 1

    def set_pending(self, count: int) -> None:
        with self._lock:
            self.pending_events = count

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "write_failures": self.write_failures,
                "transaction_rollbacks": self.transaction_rollbacks,
                "frames_persisted": self.frames_persisted,
                "detections_persisted": self.detections_persisted,
                "observations_persisted": self.observations_persisted,
                "state_transitions_persisted": self.state_transitions_persisted,
                "compliance_evaluations_persisted": self.compliance_evaluations_persisted,
                "violations_persisted": self.violations_persisted,
                "evidence_items_persisted": self.evidence_items_persisted,
                "audit_events_persisted": self.audit_events_persisted,
                "pending_events": self.pending_events,
            }
