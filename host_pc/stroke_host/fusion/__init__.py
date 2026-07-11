"""fusion 包对外接口."""
from .fusion import (
    LEVEL_DANGER,
    LEVEL_INSUFFICIENT,
    LEVEL_NORMAL,
    LEVEL_WARNING,
    FusionResult,
    fuse,
)
from .weights import WEIGHTS, normalized

__all__ = [
    "fuse",
    "FusionResult",
    "WEIGHTS",
    "normalized",
    "LEVEL_NORMAL",
    "LEVEL_WARNING",
    "LEVEL_DANGER",
    "LEVEL_INSUFFICIENT",
]
