"""PA timing engine app: instruction-driven monitoring pool and alerts."""

from .canonical import canonical_json, content_hash
from .config import DEFAULT_CONFIG, build_config
from .engine import PatimingEngine

__version__ = "1.2.0"

__all__ = [
    "PatimingEngine",
    "canonical_json",
    "content_hash",
    "build_config",
    "DEFAULT_CONFIG",
    "__version__",
]
