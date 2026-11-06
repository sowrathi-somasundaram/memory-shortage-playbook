"""Location and fingerprint of precomputed results."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .data import STRATEGIES, Params

OUT = Path(__file__).resolve().parent.parent / "precomputed"


def params_fingerprint(params: Params) -> str:
    """Changes whenever an assumption or strategy definition changes, so stale files are detected."""
    return hashlib.sha256((repr(params) + repr(STRATEGIES)).encode()).hexdigest()[:16]
