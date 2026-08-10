# api_collector_backend/utils/filetype_detection.py
from __future__ import annotations
from typing import Optional
import os


def guess_extension(filename: Optional[str], hint: Optional[str]) -> str:
    """
    Try to guess extension from filename or hint. Returns lowercase extension without dot.
    """
    if filename:
        _, ext = os.path.splitext(filename)
        if ext:
            return ext.lstrip(".").lower()
    if hint:
        return hint.lstrip(".").lower()
    return ""
