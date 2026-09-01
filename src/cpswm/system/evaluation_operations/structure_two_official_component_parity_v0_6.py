"""Pinned-official-code component parity checks for v0.6 external cores."""

from __future__ import annotations

import ast
import importlib.util
import struct
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    ActiveDreamingAdaptationInput,
    BrainctlAdaptationInput,
    CounterfactualScenario,
    FailureEpisode,
)
from cpswm.system.evaluation_operations.structure_two_external_reference_cores_v0_6 import (
    cluster_active_dreaming_failures,
    run_brainctl_reference_core,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-official-component-parity@0.6"
ACTIVE_DREAMING_COMMIT = "9c05baf41673d10e92c076ba7db18b1b6553a60d"
BRAINCTL_COMMIT = "c6348087dd07e54583f762e07bf960ac982019e6"


def _git_commit(path: Path) -> str:
    return subprocess.run(
        ("git", "-C", str(path), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _literal_assignment(path: Path, name: str) -> dict[str, float]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            value_node = node.value
            if value_node is None:
                break
            value = ast.literal_eval(value_node)
            if not isinstance(value, dict):
                break
            return {str(key): float(item) for key, item in value.items()}
    raise ValueError(f"official source has no literal mapping named {name}")


def _load_module(path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location("brainctl_write_decision", path)
    if specification is None or specification.loader is None:
        raise ValueError("cannot load official brainctl write-decision module")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _FixtureVectorDatabase:
    def __init__(self, neighbors: tuple[tuple[float, ...], ...]) -> None:
        self._neighbors = neighbors
        self._selected_neighbor: int | None = None

    def execute(self, query: str, parameters: tuple[Any, ...]) -> _FixtureVectorDatabase:
        if "FROM embeddings" in query:
            self._selected_neighbor = int(parameters[0])
        return self

    def fetchall(self) -> list[Any]:
        return [(index,) for index in range(len(self._neighbors))]

    def fetchone(self) -> tuple[bytes] | None:
        if self._selected_neighbor is None:
            return None
        return (
            struct.pack(
                f"{len(self._neighbors[self._selected_neighbor])}f",
                *self._neighbors[self._selected_neighbor],
            ),
        )


def run_official_component_parity_v0_6(
    *,
    active_dreaming_repository: Path,
    brainctl_repository: Path,
) -> dict[str, Any]:
    if _git_commit(active_dreaming_repository) != ACTIVE_DREAMING_COMMIT:
        raise ValueError("Active Dreaming checkout is not the pinned official commit")
    if _git_commit(brainctl_repository) != BRAINCTL_COMMIT:
        raise ValueError("brainctl checkout is not the pinned official commit")

    dreamer_path = active_dreaming_repository / "scalable_agent/core/dreamer.py"
    dreamer_source = dreamer_path.read_text(encoding="utf-8")
    active_checks = {
        "official_epsilon_0_3": "self.epsilon = 0.3" in dreamer_source,
        "official_min_pts_2": "self.min_pts = 2" in dreamer_source,
        "official_cosine_dbscan": "metric='cosine'" in dreamer_source,
        "official_execution_before_add_rule": (
            dreamer_source.index("verified = self._verify_rule")
            < dreamer_source.index("self.store.add_rule")
        ),
    }
    active_inputs = ActiveDreamingAdaptationInput(
        episodic_failures=(
            FailureEpisode(episode_id="f1", content="one", embedding=(1.0, 0.0)),
            FailureEpisode(episode_id="f2", content="two", embedding=(0.99, 0.01)),
            FailureEpisode(episode_id="noise", content="noise", embedding=(0.0, 1.0)),
        ),
        semantic_memory_before=(),
        counterfactual_scenarios=(
            CounterfactualScenario(
                scenario_id="scenario",
                cluster_hint="0",
                executable_payload_sha256="a" * 64,
            ),
        ),
    )
    active_checks["local_selected_dbscan_fixture_matches"] = cluster_active_dreaming_failures(
        active_inputs
    ) == (0, 0, -1)

    impl_path = brainctl_repository / "src/agentmemory/_impl.py"
    server_path = brainctl_repository / "src/agentmemory/mcp_server.py"
    write_path = brainctl_repository / "src/agentmemory/lib/write_decision.py"
    official_amac_weights = _literal_assignment(impl_path, "_AMAC_WEIGHTS")
    official_amac_priors = _literal_assignment(impl_path, "_CATEGORY_PRIORS")
    official_source_trust = _literal_assignment(server_path, "_SOURCE_TRUST_WEIGHTS")
    module = _load_module(write_path)
    official_gate_write = cast(Any, module.gate_write)
    fixtures = (
        ((1.0, 0.0), (), "decision", "agent:a", 0.9, 1.0),
        ((1.0, 0.0), ((-1.0, 0.0),), "decision", "agent:a", 0.9, 1.0),
        ((1.0, 0.0), ((0.8, 0.6),), "lesson", "project:p", 0.4, 0.5),
        ((1.0, 0.0), ((1.0, 0.0),), "other", "global", 0.2, 2.0),
    )
    fixture_results: list[dict[str, Any]] = []
    for candidate, neighbors, category, scope, confidence, arousal_gain in fixtures:
        official_score, official_reason, official_components = official_gate_write(
            candidate_blob=struct.pack("2f", *candidate),
            confidence=confidence,
            temporal_class=None,
            category=category,
            scope=scope,
            db_vec=_FixtureVectorDatabase(neighbors),
            arousal_gain=arousal_gain,
        )
        brain_inputs = BrainctlAdaptationInput(
            content="durable decision",
            candidate_embedding=candidate,
            neighbor_embeddings=neighbors,
            source="human_verified",
            source_trust=1.0,
            category=category,
            scope=scope,
            confidence=confidence,
            recall_rate=0.5,
            arousal_gain=arousal_gain,
            valence_scale=1.0,
            lifecycle_state="new",
        )
        brain_result = run_brainctl_reference_core(brain_inputs)
        fixture_results.append(
            {
                "candidate": candidate,
                "neighbors": neighbors,
                "category": category,
                "scope": scope,
                "novelty_matches": abs(
                    float(brain_result.output["novelty"]) - float(official_components["novelty"])
                )
                < 1e-4,
                "score_matches": abs(
                    float(brain_result.output["worthiness_score"]) - float(official_score)
                )
                < 1e-4,
                "acceptance_matches": (official_reason == "")
                == (brain_result.output["write_tier"] != "SKIP"),
            }
        )
    brain_result = run_brainctl_reference_core(
        BrainctlAdaptationInput(
            content="durable decision",
            candidate_embedding=(1.0, 0.0),
            neighbor_embeddings=(),
            source="human_verified",
            source_trust=1.0,
            category="decision",
            scope="agent:a",
            confidence=0.9,
            recall_rate=0.5,
            arousal_gain=1.0,
            valence_scale=1.0,
            lifecycle_state="new",
        )
    )
    expected_pre = (
        official_amac_weights["future_utility"] * 0.5
        + official_amac_weights["factual_confidence"] * official_source_trust["human_verified"]
        + official_amac_weights["semantic_novelty"] * 1.0
        + official_amac_weights["temporal_recency"] * 1.0
        + official_amac_weights["content_type_prior"] * official_amac_priors["decision"]
    )
    brain_checks = {
        "official_source_trust_mapping_loaded": official_source_trust
        == {
            "human_verified": 1.0,
            "mcp_tool": 0.85,
            "llm_inference": 0.7,
            "external_doc": 0.5,
        },
        "amac_pre_gate_matches_official_literals": abs(
            float(brain_result.output["pre_worthiness"]) - expected_pre
        )
        < 1e-12,
        "selected_fixture_novelty_matches": all(
            bool(item["novelty_matches"]) for item in fixture_results
        ),
        "selected_fixture_w_m_score_matches": all(
            bool(item["score_matches"]) for item in fixture_results
        ),
        "selected_fixture_acceptance_matches": all(
            bool(item["acceptance_matches"]) for item in fixture_results
        ),
        "negative_similarity_fixture_included": any(
            item["neighbors"] == ((-1.0, 0.0),) for item in fixture_results
        ),
        "current_official_valence_not_applied_to_w_m_score": (
            "_valence_scale" not in write_path.read_text(encoding="utf-8")
        ),
    }
    selected_fixture_parity_passed = all(active_checks.values()) and all(brain_checks.values())
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "active_dreaming_commit": ACTIVE_DREAMING_COMMIT,
        "brainctl_commit": BRAINCTL_COMMIT,
        "active_dreaming_component_checks": active_checks,
        "brainctl_component_checks": brain_checks,
        "brainctl_selected_fixture_results": fixture_results,
        "selected_fixture_parity_passed": selected_fixture_parity_passed,
        "component_parity_passed": False,
        "native_protocol_reproduction_passed": False,
        "adaptation_parity_passed": False,
        "claim_boundary": (
            "Only the explicitly listed fixtures were compared against pinned official "
            "code. Passing them is not whole-component parity, native-protocol "
            "reproduction, adaptation parity, or efficacy evidence. Active Dreaming "
            "scenario execution is outside this selected DBSCAN fixture report."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "ACTIVE_DREAMING_COMMIT",
    "BRAINCTL_COMMIT",
    "PROTOCOL_ID",
    "run_official_component_parity_v0_6",
]
