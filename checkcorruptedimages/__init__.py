#!/usr/bin/env python3

from importlib.metadata import version as _package_version

from checkcorruptedimages._result import ImageCheckResult
from checkcorruptedimages.checkcorruptedimages import (
    CheckCorruptedImages,
    CheckSession,
    )

__version__ = _package_version("checkcorruptedimages")

__all__ = [
    "CheckCorruptedImages",
    "CheckSession",
    "ImageCheckResult",
    "__version__",
    ]
