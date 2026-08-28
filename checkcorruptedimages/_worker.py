#!/usr/bin/env python3

"""
Sacrificial worker process: fully decodes images with Pillow, one
JSON-line request per image on stdin, one JSON-line response on
stdout. A decoder crash only kills this process; the parent pool
respawns it and the batch continues.
"""

import json
import signal
import sys
import warnings

from PIL import Image, ImageFile

# Optional HEIC/HEIF support: installed via checkcorruptedimages[heif].
try:
    import pillow_heif
except ImportError:
    pass
else:
    pillow_heif.register_heif_opener()

MAX_REASON_LENGTH = 300


def configure(regard_warnings: bool) -> None:
    """
    Configure Pillow strictness.
    :param regard_warnings: bool: strict mode; truncated files that
        would still partially decode count as corruption.
    """
    ImageFile.LOAD_TRUNCATED_IMAGES = not regard_warnings


def check_one(path: str, regard_warnings: bool) -> tuple[str, str | None]:
    """
    Fully decode one image.
    :param path: str: Image path.
    :param regard_warnings: bool: Escalate Pillow warnings (e.g.
        DecompressionBombWarning) to corruption.

    """
    try:
        with warnings.catch_warnings():
            if regard_warnings:
                warnings.simplefilter("error")
                # API-lifecycle warnings say nothing about the image.
                warnings.simplefilter("ignore", DeprecationWarning)
                warnings.simplefilter("ignore", PendingDeprecationWarning)
                warnings.simplefilter("ignore", FutureWarning)
            else:
                warnings.simplefilter("ignore")
            with Image.open(path) as image:
                image.load()
    except Exception as error:  # noqa: BLE001 - any decode failure is corruption
        reason = f"{type(error).__name__}: {error}"
        return "corrupted", reason[:MAX_REASON_LENGTH]
    return "ok", None


def _apply_memory_limit(max_bytes: int) -> None:
    """Best-effort address-space cap; unavailable on Windows."""
    try:
        import resource
    except ImportError:
        return
    try:
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    except (OSError, ValueError):
        pass


def main() -> None:
    # A terminal Ctrl-C signals the whole process group; the parent
    # pool must stay in charge of worker shutdown.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    arguments = sys.argv[1:]

    if "--max-memory" in arguments:
        _apply_memory_limit(
            int(arguments[arguments.index("--max-memory") + 1])
            )

    regard_warnings = "--lenient" not in arguments

    configure(regard_warnings=regard_warnings)

    print(json.dumps({"status": "ready"}), flush=True)

    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        status, reason = check_one(
            path=request["path"], regard_warnings=regard_warnings
            )
        print(json.dumps({"status": status, "reason": reason}), flush=True)


if __name__ == "__main__":
    main()
