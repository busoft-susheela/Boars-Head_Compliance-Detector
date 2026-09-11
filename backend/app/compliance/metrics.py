"""ComplianceMetrics — counters and timings for the compliance pipeline.

Thread-safe counters incremented by ComplianceRuleEngine and ComplianceWorker.
Structured to mirror InferenceMetrics so the health endpoint can expose them
consistently.
"""

from __future__ import annotations

import threading
import time


class ComplianceMetrics:
    """Thread-safe metrics for the compliance rule engine.

    All counters are monotonically increasing.  ``snapshot()`` returns
    a plain dict suitable for the health endpoint.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evaluations: int = 0
        self._violations: int = 0
        self._evaluation_failures: int = 0
        self._state_store_gets: int = 0
        self._state_store_sets: int = 0
        self._evidence_groups_created: int = 0
        self._evidence_groups_discarded: int = 0
        self._evidence_groups_confirmed: int = 0
        self._evidence_publish_failures: int = 0
        self._frames_processed: int = 0
        self._last_evaluation_duration: float = 0.0

    # ── Increment helpers ────────────────────────────────────────────────────

    def record_evaluation(self, duration_seconds: float) -> None:
        with self._lock:
            self._evaluations += 1
            self._frames_processed += 1
            self._last_evaluation_duration = duration_seconds

    def record_violation(self) -> None:
        with self._lock:
            self._violations += 1
            self._evidence_groups_confirmed += 1

    def record_evaluation_failure(self) -> None:
        with self._lock:
            self._evaluation_failures += 1

    def record_state_store_get(self) -> None:
        with self._lock:
            self._state_store_gets += 1

    def record_state_store_set(self) -> None:
        with self._lock:
            self._state_store_sets += 1

    def record_group_created(self) -> None:
        with self._lock:
            self._evidence_groups_created += 1

    def record_group_discarded(self) -> None:
        with self._lock:
            self._evidence_groups_discarded += 1

    def record_evidence_publish_failure(self) -> None:
        with self._lock:
            self._evidence_publish_failures += 1

    # ── Snapshot ─────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "evaluations_total": self._evaluations,
                "violations_total": self._violations,
                "evaluation_failures_total": self._evaluation_failures,
                "state_store_gets_total": self._state_store_gets,
                "state_store_sets_total": self._state_store_sets,
                "evidence_groups_created_total": self._evidence_groups_created,
                "evidence_groups_discarded_total": self._evidence_groups_discarded,
                "evidence_groups_confirmed_total": self._evidence_groups_confirmed,
                "evidence_publish_failures_total": self._evidence_publish_failures,
                "frames_processed_total": self._frames_processed,
                "last_evaluation_duration_seconds": round(
                    self._last_evaluation_duration, 6
                ),
            }
