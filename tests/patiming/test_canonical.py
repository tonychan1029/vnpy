from vnpy_patiming.canonical import canonical_json, content_hash


def test_key_order_and_null_equivalence():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"a": 1, "b": None}) == canonical_json({"a": 1})


def test_numeric_normalization():
    assert canonical_json({"p": 100}) == canonical_json({"p": 100.0})


def test_hash_golden():
    payload = {
        "symbol": "rb2501.SHFE",
        "direction": "both",
        "key_levels": {"prior_high": 100.0},
        "producer_revision": 3,
    }
    assert content_hash(payload) == content_hash(dict(reversed(list(payload.items()))))
    assert content_hash(payload) != content_hash({**payload, "direction": "long"})
