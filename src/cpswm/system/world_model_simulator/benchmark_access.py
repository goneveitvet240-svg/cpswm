"""Explicit capability for evaluator-only access to simulator ground truth.

This is an API boundary, not a Python security sandbox.  Robot-facing callers
use :meth:`SymbolicWorldModelSimulator.run`, which never returns privileged
truth.  Benchmark and evaluation code must deliberately import this module and
request the nominal capability before calling ``run_privileged``.
"""

from __future__ import annotations

_CAPABILITY_SEAL = object()


class BenchmarkGroundTruthCapability:
    """Nominal token issued by this benchmark-only module.

    It prevents accidental use of the privileged API.  It is not a security
    capability against hostile Python code in the same process.
    """

    __slots__ = ("_seal",)

    def __init__(self, seal: object) -> None:
        if seal is not _CAPABILITY_SEAL:
            raise PermissionError("ground-truth capability must be issued by benchmark_access")
        self._seal = seal


def issue_benchmark_ground_truth_capability() -> BenchmarkGroundTruthCapability:
    """Issue the explicit token required by benchmark/evaluation code."""

    return BenchmarkGroundTruthCapability(_CAPABILITY_SEAL)


def require_benchmark_ground_truth_capability(
    capability: BenchmarkGroundTruthCapability,
) -> None:
    """Reject missing, forged, or wrong-purpose capability objects."""

    if (
        not isinstance(capability, BenchmarkGroundTruthCapability)
        or capability._seal is not _CAPABILITY_SEAL
    ):
        raise PermissionError("a valid benchmark ground-truth capability is required")


__all__ = [
    "BenchmarkGroundTruthCapability",
    "issue_benchmark_ground_truth_capability",
]
