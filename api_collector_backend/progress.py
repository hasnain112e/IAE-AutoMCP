# api_collector_backend/progress.py
from __future__ import annotations

from typing import Callable, Optional

# This will be set by app.py at startup
_progress_sender: Optional[Callable[[str], None]] = None


def set_sender(sender: Callable[[str], None]) -> None:
    """
    Called from app.py to connect progress reporting to the WebSocket manager.
    """
    global _progress_sender
    _progress_sender = sender


def report(message: str) -> None:
    """
    Call this from anywhere (parsers, collectors, etc.) to report progress.

    - Always prints to stdout (so you see it in backend logs).
    - If a sender is registered, forwards to the WebSocket progress stream.
    """
    print(message)
    if _progress_sender is not None:
        try:
            _progress_sender(message)
        except Exception:
            # Don't ever blow up the main logic just because progress failed
            pass
