"""Independent-stratum proposal draws; no actor-specific quotas or target changes."""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_right
from collections.abc import Sequence

STRATIFIED_POLICY = "independent_strata_v1"


def stratum_offsets(count: int, seed_sha256: str) -> tuple[float, ...]:
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("draw count must be a positive integer")
    if len(seed_sha256) != 64 or any(c not in "0123456789abcdef" for c in seed_sha256):
        raise ValueError("seed must be a lowercase SHA256 digest")
    # Separate domain and index for each stratum, shared by the two native arms.
    # Retain 53 bits so float conversion never rounds the upper endpoint to 1.
    return tuple(
        (
            int.from_bytes(
                hashlib.sha256(f"{STRATIFIED_POLICY}:{seed_sha256}:{i}".encode()).digest()[:8],
                "big",
            )
            >> 11
        )
        / float(1 << 53)
        for i in range(count)
    )


def stratified_draw_indices(
    probabilities: Sequence[float], count: int, seed_sha256: str
) -> tuple[int, ...]:
    offsets = stratum_offsets(count, seed_sha256)
    if not probabilities or any(not math.isfinite(p) or p < 0 for p in probabilities):
        raise ValueError("proposal must contain finite nonnegative mass")
    total = math.fsum(probabilities)
    if not math.isfinite(total) or abs(total - 1.0) > 1e-9:
        raise ValueError("proposal must be normalized")
    cdf = []
    running = 0.0
    for p in probabilities:
        running += p / total
        cdf.append(running)
    cdf[-1] = 1.0
    return tuple(
        bisect_right(cdf, min((i + u) / count, math.nextafter(1.0, 0.0)))
        for i, u in enumerate(offsets)
    )
