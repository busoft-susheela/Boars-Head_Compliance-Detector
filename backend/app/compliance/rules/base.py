"""RuleEvaluator ABC and RuleEvaluationResult.

Responsibility: define the contract between the ComplianceRuleEngine and
any concrete rule implementation.

The evaluator is a pure domain component.  It must NOT:
  - call StateStore.get() / StateStore.set()
  - call MessageQueue.publish()
  - import asyncio
  - access Redis, Kafka, or any external service
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.app.compliance.evidence.models import EvidencePayload
from backend.app.compliance.temporal.models import TemporalMetrics


@dataclass(frozen=True)
class RuleEvaluationResult:
    """Typed return value of ``RuleEvaluator.evaluate()``.

    Attributes:
        person_state: Updated serialisable person state dict to be persisted
                      by the engine.  The evaluator returns the updated copy;
                      the engine is responsible for writing it to StateStore.
        outcome:      ``"violation"`` when a new violation is confirmed for
                      this frame; ``None`` for normal (non-alerting) processing.
                      Subsequent frames after confirmation return ``None``
                      (idempotency — one alert per group_id).
        evidence:     Frozen EvidencePayload when outcome == "violation";
                      ``None`` otherwise.
    """

    person_state: dict
    outcome: str | None
    evidence: EvidencePayload | None


class RuleEvaluator(ABC):
    """Backend-independent interface for compliance rule evaluation.

    A rule evaluator receives the current person state, temporal metrics,
    and frame metadata, then returns an updated state and optional outcome.

    Implementations may maintain in-memory evidence buffers but must NOT
    own persistence or message publishing.
    """

    @abstractmethod
    def evaluate(
        self,
        person_state: dict,
        metrics: TemporalMetrics,
        camera_id: str,
        zone_id: str,
        timestamp,
        thumbnail: bytes | None,
        frame_id: int,
        source_fps: float = 0.0,
    ) -> RuleEvaluationResult:
        """Apply the rule to the current state and metrics.

        Args:
            person_state: Current serialisable person state (from StateStore).
            metrics:      Temporal measurements from SpatioTemporalAnalyzer.
            camera_id:    Source camera identifier.
            zone_id:      Zone within the camera.
            timestamp:    Frame capture time (datetime).
            thumbnail:    JPEG evidence bytes; None if unavailable.
            frame_id:     Monotonic frame counter.

        Returns:
            :class:`RuleEvaluationResult` with updated state, optional
            outcome, and optional evidence payload.
        """
