from __future__ import annotations

import pytest

from cpswm.system.reproducibility import canonical_json, content_sha256


def test_canonical_json_rejects_mapping_key_collision() -> None:
    with pytest.raises(ValueError, match="collide"):
        canonical_json({1: "attacker", "1": "trusted"})


def test_canonical_hash_is_order_invariant_for_safe_mapping() -> None:
    assert content_sha256({"a": 1, "b": 2}) == content_sha256({"b": 2, "a": 1})
