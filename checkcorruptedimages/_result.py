#!/usr/bin/env python3

from dataclasses import dataclass
from pathlib import Path

REASON_TIMEOUT = "timeout"
REASON_CRASHED = "decoder crashed"


@dataclass(frozen=True)
class ImageCheckResult:
    """
    Result of checking one image.
    reason is None for a clean image and a short description of the
        failure for a corrupted one.
    """

    file_path: Path
    corrupted: bool
    reason: str | None = None
