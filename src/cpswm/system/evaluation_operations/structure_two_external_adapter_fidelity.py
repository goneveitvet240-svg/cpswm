"""Independent fidelity gate for external Structure-Two adapters.

Gate B establishes behavioral distinguishability on the common interface.  It
does not establish that an adapter reproduces the official external method.
This module keeps those claims separate and fails closed until every external
arm has a content-bound, independently checked full-method reproduction.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-external-adapter-fidelity-gate@0.1"


class AdapterFidelityVerdict(StrEnum):
    FAITHFUL_REPRODUCTION = "faithful_reproduction"
    NON_FAITHFUL_PROXY = "non_faithful_proxy"
    NOT_INDEPENDENTLY_AUDITED = "not_independently_audited"


_AUDIT_ROWS: dict[str, dict[str, Any]] = {
    "corrected_amg": {
        "method": "Damen-Hogg AMG",
        "verdict": AdapterFidelityVerdict.NOT_INDEPENDENTLY_AUDITED,
        "official_source": None,
        "official_code_commit": None,
        "verified_components": (),
        "missing_or_changed_components": (
            "primary-source and official-code semantic audit",
            "published-protocol result recheck",
        ),
    },
    "o_star_matched": {
        "method": "O-STaR",
        "verdict": AdapterFidelityVerdict.NON_FAITHFUL_PROXY,
        "official_source": (
            "https://www.hrl.uni-bonn.de/publications/2026/menon26grc/"
            "menon26grc_paper_poster.pdf/@@download/file"
        ),
        "official_code_commit": None,
        "verified_components": (),
        "missing_or_changed_components": (
            "LLM Day-0 semantic prior",
            "3D geometric candidate pruning and dynamic scene graph",
            "Dirichlet-Categorical hit and miss updates",
            "Stay+Leak and relaxed transition inference",
            "cost-aware active search",
            "opportunistic multi-target perception",
            "published physical and HOMER+ protocol recheck",
        ),
        "local_adapter_observation": (
            "Gate B instantiates _CountMethod(mode='o_star'); it does not use the "
            "separate OStarReferenceBelief equation core."
        ),
    },
    "active_dreaming_matched": {
        "method": "Active Dreaming Memory",
        "verdict": AdapterFidelityVerdict.NON_FAITHFUL_PROXY,
        "official_source": "https://engrxiv.org/preprint/download/5919/9826/8234",
        "official_code_url": "https://github.com/KasimVali2207/active-dreaming-memory",
        "official_code_commit": "9c05baf41673d10e92c076ba7db18b1b6553a60d",
        "verified_components": (),
        "missing_or_changed_components": (
            "failure-episode retrieval and episodic/semantic dual-store lifecycle",
            "embedding-based DBSCAN failure clustering",
            "LLM rule abstraction",
            "LLM counterfactual executable-scenario generation",
            "actual scenario execution before semantic-memory insertion",
            "official evaluation protocol and published-result recheck",
        ),
        "local_adapter_observation": (
            "The adapter applies a confidence-entropy-coverage threshold and marks a "
            "local verifier as executed without running the official dreaming pipeline."
        ),
    },
    "auto_dreamer_matched": {
        "method": "Auto-Dreamer",
        "verdict": AdapterFidelityVerdict.NOT_INDEPENDENTLY_AUDITED,
        "official_source": None,
        "official_code_commit": None,
        "verified_components": (),
        "missing_or_changed_components": (
            "primary-source and official-code semantic audit",
            "published-protocol result recheck",
        ),
    },
    "trustmem_matched": {
        "method": "TrustMem",
        "verdict": AdapterFidelityVerdict.NOT_INDEPENDENTLY_AUDITED,
        "official_source": None,
        "official_code_commit": None,
        "verified_components": (),
        "missing_or_changed_components": (
            "primary-source and official-code semantic audit",
            "published-protocol result recheck",
        ),
    },
    "brainctl_matched": {
        "method": "brainctl",
        "verdict": AdapterFidelityVerdict.NON_FAITHFUL_PROXY,
        "official_source": "https://www.brainctl.org/whitepaper",
        "official_code_url": "https://github.com/TSchonleber/brainctl",
        "official_code_commit": "c6348087dd07e54583f762e07bf960ac982019e6",
        "verified_components": (
            "the adapter copies the whitepaper's five top-level worthiness weights",
        ),
        "missing_or_changed_components": (
            "source-trust categories and category-specific priors",
            "embedding-based semantic novelty",
            "scope, historical recall, arousal, and valence factors",
            "two-stage write-decision gate and tier routing",
            "Bayesian confidence, merge, supersede, rejection, and consolidation lifecycle",
            "official evaluation protocol and result recheck",
        ),
        "local_adapter_observation": (
            "The adapter maps a simplified weighted score directly to embodied-state "
            "promotion/escrow, although brainctl describes a memory-control layer rather "
            "than a planner."
        ),
    },
}


def build_external_adapter_fidelity_audit(expected_arms: Sequence[str]) -> dict[str, Any]:
    """Return a deterministic fail-closed audit for external arms in a Gate B set."""

    rows: list[dict[str, Any]] = []
    for arm in expected_arms:
        if arm not in _AUDIT_ROWS:
            continue
        rows.append({"arm": arm, **_AUDIT_ROWS[arm]})
    verdicts = {str(row["verdict"]) for row in rows}
    passed = bool(rows) and verdicts == {AdapterFidelityVerdict.FAITHFUL_REPRODUCTION}
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "claim_boundary": (
            "Gate B behavioral distinguishability is necessary but insufficient for "
            "external-method fidelity or efficacy comparison."
        ),
        "audited_external_arms": rows,
        "required_external_arm_count": len(rows),
        "external_fidelity_gate_passed": passed,
        "external_method_efficacy_comparison_allowed": passed,
        "completion_rule": (
            "Every external arm must be faithful_reproduction with content-bound primary "
            "source, official-code semantics where available, executable component tests, "
            "and a published-protocol result recheck."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "PROTOCOL_ID",
    "AdapterFidelityVerdict",
    "build_external_adapter_fidelity_audit",
]
