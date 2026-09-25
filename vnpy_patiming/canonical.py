"""Canonical JSON serialization and content hashing (spec 3.1)."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("non-finite float cannot be hashed")
        if value.is_integer():
            return int(value)
        return round(value, 10)
    if isinstance(value, dict):
        cleaned = {k: _normalize(v) for k, v in value.items() if v is not None}
        return {k: cleaned[k] for k in sorted(cleaned)}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def canonical_json(mapping: dict) -> str:
    """Compact JSON with sorted keys; missing and null are equivalent."""
    normalized = _normalize(mapping)
    if normalized is None:
        normalized = {}
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def content_hash(mapping: dict) -> str:
    """SHA-256 hex digest of the canonical form; computed only by the write path."""
    return hashlib.sha256(canonical_json(mapping).encode("utf-8")).hexdigest()
