"""Sampler ABC — decides whether the current frame should be processed."""

from abc import ABC, abstractmethod


class Sampler(ABC):
    @abstractmethod
    def should_process(self) -> bool:
        """Return True if this frame should be forwarded to the inference pipeline."""
