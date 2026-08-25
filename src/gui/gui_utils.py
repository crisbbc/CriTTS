"""Shared state helpers for the main window."""
from dataclasses import dataclass
from typing import Optional


class STTState:
    """State machine states for Speech-to-Text operations."""
    IDLE = "idle"                    # Ready to record
    RECORDING = "recording"          # Currently recording audio
    TRANSCRIBING = "transcribing"    # Processing audio (transcription in progress)
    ERROR = "error"                  # Error state (will auto-reset)


@dataclass(frozen=True)


class DeferredTextAnalysisRequest:
    """Token identifying one deferred text-analysis request.

    The analyzed text is intentionally *not* carried here: reading the whole
    text widget on every keystroke is the dominant cost of the voice-indicator
    update path, so the current document is read lazily once the debounce
    timer actually fires (and only when this request is still the latest).
    """
    generation: int
    text: Optional[str] = None


class LatestWinsTextAnalysisScheduler:
    """Track deferred analysis requests so only the newest one may apply."""

    def __init__(self):
        self._latest_generation = 0

    def next_request(self, text: Optional[str] = None) -> DeferredTextAnalysisRequest:
        self._latest_generation += 1
        return DeferredTextAnalysisRequest(generation=self._latest_generation, text=text)

    def is_latest(self, request: DeferredTextAnalysisRequest) -> bool:
        return request.generation == self._latest_generation
