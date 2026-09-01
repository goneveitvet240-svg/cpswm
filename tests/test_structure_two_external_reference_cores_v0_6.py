from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.oam_phm_external_evidence import OStarReferenceConfig
from cpswm.system.evaluation_operations.structure_two_counterfactual_executor_v0_7 import (
    ATTESTATION_DOMAIN,
    MAX_INSTRUCTIONS,
    MAX_PROGRAM_BYTES,
    MAX_STATE_KEYS,
    CounterfactualExecutionReceipt,
    CounterfactualScenarioProgram,
    attested_execution_payload,
    execute_counterfactual_scenario,
)
from cpswm.system.evaluation_operations.structure_two_external_inputs_v0_6 import (
    ActiveDreamingAdaptationInput,
    AMGAdaptationInput,
    AMGCrossEventConstraint,
    AMGEventEvidence,
    AutoDreamerAdaptationInput,
    BrainctlAdaptationInput,
    CompleteExternalAdaptationInputsV06,
    CounterfactualScenario,
    FailureEpisode,
    OStarAdaptationInput,
    OStarObservation,
    OStarSceneNode,
    ProvenanceTrajectory,
    TrustMemAdaptationInput,
    TrustMemStateItem,
    TrustMemTransition,
    TypedMemory,
)
from cpswm.system.evaluation_operations.structure_two_external_reference_cores_v0_6 import (
    mechanism_receipts_from_reference_core,
    run_active_dreaming_reference_core,
    run_amg_reference_core,
    run_auto_dreamer_reference_core,
    run_brainctl_reference_core,
    run_o_star_reference_core,
    run_trustmem_reference_core,
)
from cpswm.system.evaluation_operations.structure_two_six_arm_execution_v0_7 import (
    ATTESTATION_DOMAIN as SIX_ARM_ATTESTATION_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_six_arm_execution_v0_7 import (
    CANONICAL_SIX_ARMS,
    run_six_arm_reference_execution_v0_7,
    verify_six_arm_reference_execution_v0_7,
)
from cpswm.system.reproducibility import content_sha256

HASH_A = "a" * 64
HASH_B = "b" * 64


def _amg_event(event_id: str, *, actor_a: float, actor_b: float) -> AMGEventEvidence:
    return AMGEventEvidence(
        event_id=event_id,
        source_likelihood=0.8,
        actor_likelihoods={"a": actor_a, "b": actor_b},
        mechanism_likelihoods={"direct": 0.7, "handoff": 0.3},
        ordered_role_likelihoods={"a->b": 0.6, "b->a": 0.4},
    )


def test_amg_runs_one_constrained_global_map_across_events() -> None:
    inputs = AMGAdaptationInput(
        events=(
            _amg_event("e1", actor_a=0.9, actor_b=0.1),
            _amg_event("e2", actor_a=0.8, actor_b=0.2),
        ),
        hierarchy_edges=(("e1", "e2"),),
        cross_event_constraints=(
            AMGCrossEventConstraint(
                kind="same_responsible_actor",
                left_event_id="e1",
                right_event_id="e2",
            ),
        ),
    )
    result = run_amg_reference_core(inputs)
    selected = result.output["selected_parse"]
    assert {item["responsible_actor"] for item in selected} == {"a"}
    assert tuple(item.event for item in result.transitions) == ("global_multi_event_map_inference",)


def test_amg_rejects_an_incomplete_ordered_role_support() -> None:
    with pytest.raises(ValidationError, match="every distinct actor pair"):
        AMGEventEvidence(
            event_id="e",
            source_likelihood=0.8,
            actor_likelihoods={"a": 0.8, "b": 0.2},
            mechanism_likelihoods={"direct": 0.7, "handoff": 0.3},
            ordered_role_likelihoods={"a->b": 0.6},
        )


def _o_star() -> OStarAdaptationInput:
    return OStarAdaptationInput(
        scene_nodes=(
            OStarSceneNode(node_id="room", node_type="room"),
            OStarSceneNode(node_id="drawer", node_type="compartment", parent_id="room"),
            OStarSceneNode(node_id="desk", node_type="furniture", parent_id="room"),
        ),
        feasible_target_locations={"keys": ("drawer", "desk")},
        llm_day_zero_priors={"keys": {"drawer": 0.75, "desk": 0.25}},
        observations=(
            OStarObservation(target_id="keys", location_id="desk", outcome="miss"),
            OStarObservation(
                target_id="other", location_id="drawer", outcome="hit", opportunistic=True
            ),
        ),
        navigation_and_inspection_costs={"drawer": 2.0, "desk": 1.0},
    )


def test_o_star_input_fails_without_opportunistic_observation() -> None:
    payload = _o_star().model_dump()
    payload["observations"] = [{"target_id": "keys", "location_id": "desk", "outcome": "miss"}]
    with pytest.raises(ValidationError, match="opportunistic"):
        OStarAdaptationInput.model_validate(payload)


def test_o_star_core_runs_paper_equations_and_cost_ranking() -> None:
    result = run_o_star_reference_core(
        _o_star(),
        target_id="keys",
        config=OStarReferenceConfig(
            initial_pseudocount_mass=10.0,
            hit_weight=3.0,
            miss_weight=2.0,
            leak_rate=0.2,
        ),
    )
    assert result.arm == "o_star_matched"
    assert result.output["search_order"][0] in {"drawer", "desk"}
    assert {item.event for item in result.transitions} == {
        "dirichlet_hit_or_miss_update",
        "stay_leak_transition",
        "cost_aware_search",
    }
    receipts = mechanism_receipts_from_reference_core(
        result,
        invocation_prefix="episode:step",
        implementation_bundle_sha256=HASH_A,
    )
    assert tuple(item.event for item in receipts) == tuple(
        item.event for item in result.transitions
    )
    assert all(item.implementation_bundle_sha256 == HASH_A for item in receipts)


def _active_failures() -> tuple[FailureEpisode, ...]:
    return (
        FailureEpisode(episode_id="f1", content="failure one", embedding=(1.0, 0.0)),
        FailureEpisode(episode_id="f2", content="failure two", embedding=(0.99, 0.01)),
        FailureEpisode(episode_id="noise", content="noise", embedding=(0.0, 1.0)),
    )


def _active(payload_sha256: str) -> ActiveDreamingAdaptationInput:
    return ActiveDreamingAdaptationInput(
        episodic_failures=_active_failures(),
        semantic_memory_before=("existing",),
        counterfactual_scenarios=(
            CounterfactualScenario(
                scenario_id="dream-0",
                cluster_hint="0",
                executable_payload_sha256=payload_sha256,
            ),
        ),
    )


def _scenario_evidence(
    tmp_path: Path,
    *,
    expected_attempts: int = 1,
    scenario_id: str = "dream-0",
    cluster_id: int = 0,
    failure_set_sha256: str | None = None,
    rule: str = "rule",
) -> tuple[
    Path,
    CounterfactualExecutionReceipt,
    Ed25519AttestationSigner,
]:
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "structure-two-counterfactual-scenario@0.7",
                "scenario_id": scenario_id,
                "cluster_id": cluster_id,
                "failure_set_sha256": failure_set_sha256 or content_sha256(_active_failures()[:2]),
                "candidate_rule_sha256": content_sha256(rule),
                "initial_state": {"attempts": 0},
                "instructions": [
                    {"operation": "increment", "key": "attempts", "value": 1},
                    {"operation": "assert_equals", "key": "attempts", "value": 1},
                ],
                "expected_final_state": {"attempts": expected_attempts},
            }
        ),
        encoding="utf-8",
    )
    signer = Ed25519AttestationSigner.generate(key_id="scenario-executor")
    return path, execute_counterfactual_scenario(path, signer=signer), signer


def _run_active_with_evidence(tmp_path: Path, *, expected_attempts: int = 1):
    path, receipt, signer = _scenario_evidence(tmp_path, expected_attempts=expected_attempts)
    verifier = signer.verifier()
    inputs = _active(hashlib.sha256(path.read_bytes()).hexdigest())
    return run_active_dreaming_reference_core(
        inputs,
        abstracted_rule_by_cluster={0: "rule"},
        scenario_execution_receipts={"dream-0": receipt},
        scenario_program_paths={"dream-0": path},
        trusted_executor_key_id=verifier.key_id,
        trusted_executor_public_key_sha256=verifier.public_key_sha256,
    )


def test_active_dreaming_commits_only_after_attested_execution(tmp_path: Path) -> None:
    passed = _run_active_with_evidence(tmp_path)
    assert passed.output["committed_rules"] == ("rule",)
    assert passed.output["verified_execution_receipt_count"] == 1
    assert passed.output["scenario_execution_performed_by_resource_bounded_executor"] is True
    assert passed.output["commit_gate_basis"] == "cluster_failure_rule_bound_executor_receipt"
    assert "counterfactual_scenario_executed_with_attested_receipt" in {
        item.event for item in passed.transitions
    }


def test_active_dreaming_rejects_failed_execution_receipt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="did not succeed"):
        _run_active_with_evidence(tmp_path, expected_attempts=2)


def test_active_dreaming_rejects_tampered_payload_after_execution(tmp_path: Path) -> None:
    path, receipt, signer = _scenario_evidence(tmp_path)
    original_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expected_final_state"] = {"attempts": 9}
    path.write_text(json.dumps(payload), encoding="utf-8")
    verifier = signer.verifier()
    with pytest.raises(ValueError, match="payload hash mismatch"):
        run_active_dreaming_reference_core(
            _active(original_sha256),
            abstracted_rule_by_cluster={0: "rule"},
            scenario_execution_receipts={"dream-0": receipt},
            scenario_program_paths={"dream-0": path},
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
        )


def test_active_dreaming_rejects_untrusted_executor(tmp_path: Path) -> None:
    path, receipt, _signer = _scenario_evidence(tmp_path)
    attacker = Ed25519AttestationSigner.generate(key_id="attacker").verifier()
    with pytest.raises(ValueError, match="executor is not trusted"):
        run_active_dreaming_reference_core(
            _active(hashlib.sha256(path.read_bytes()).hexdigest()),
            abstracted_rule_by_cluster={0: "rule"},
            scenario_execution_receipts={"dream-0": receipt},
            scenario_program_paths={"dream-0": path},
            trusted_executor_key_id=attacker.key_id,
            trusted_executor_public_key_sha256=attacker.public_key_sha256,
        )


def test_active_dreaming_rejects_receipt_tampering_after_signature(tmp_path: Path) -> None:
    path, receipt, signer = _scenario_evidence(tmp_path)
    verifier = signer.verifier()
    tampered = receipt.model_copy(update={"final_state_sha256": HASH_B})
    with pytest.raises(AttestationError, match="signature does not match"):
        run_active_dreaming_reference_core(
            _active(hashlib.sha256(path.read_bytes()).hexdigest()),
            abstracted_rule_by_cluster={0: "rule"},
            scenario_execution_receipts={"dream-0": tampered},
            scenario_program_paths={"dream-0": path},
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
        )


def test_active_dreaming_rejects_missing_execution_receipt(tmp_path: Path) -> None:
    path, _receipt, signer = _scenario_evidence(tmp_path)
    verifier = signer.verifier()
    with pytest.raises(ValueError, match="receipts must exactly cover scenarios"):
        run_active_dreaming_reference_core(
            _active(hashlib.sha256(path.read_bytes()).hexdigest()),
            abstracted_rule_by_cluster={0: "rule"},
            scenario_execution_receipts={},
            scenario_program_paths={"dream-0": path},
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
        )


def test_active_dreaming_rejects_zero_cluster_false_positive() -> None:
    inputs = ActiveDreamingAdaptationInput(
        episodic_failures=(
            FailureEpisode(episode_id="x", content="x", embedding=(1.0, 0.0)),
            FailureEpisode(episode_id="y", content="y", embedding=(0.0, 1.0)),
            FailureEpisode(episode_id="z", content="z", embedding=(-1.0, 0.0)),
        ),
        semantic_memory_before=(),
        counterfactual_scenarios=(
            CounterfactualScenario(
                scenario_id="unused",
                cluster_hint="0",
                executable_payload_sha256=HASH_A,
            ),
        ),
    )
    with pytest.raises(ValueError, match="no non-noise failure cluster"):
        run_active_dreaming_reference_core(
            inputs,
            abstracted_rule_by_cluster={},
            scenario_execution_receipts={},
            scenario_program_paths={},
            trusted_executor_key_id="unused",
            trusted_executor_public_key_sha256=HASH_A,
        )


@pytest.mark.parametrize(
    ("changed_field", "message"),
    (
        ("scenario_id", "scenario ids must be unique"),
        ("cluster_hint", "cluster hints must be unique"),
    ),
)
def test_active_dreaming_rejects_duplicate_scenario_identity(
    changed_field: str, message: str
) -> None:
    payload = _active(HASH_A).model_dump()
    duplicate = dict(payload["counterfactual_scenarios"][0])
    duplicate["scenario_id"] = "dream-1"
    duplicate["cluster_hint"] = "1"
    duplicate[changed_field] = payload["counterfactual_scenarios"][0][changed_field]
    payload["counterfactual_scenarios"] = [
        payload["counterfactual_scenarios"][0],
        duplicate,
    ]
    with pytest.raises(ValidationError, match=message):
        ActiveDreamingAdaptationInput.model_validate(payload)


def test_active_dreaming_rejects_rule_binding_replay(tmp_path: Path) -> None:
    path, receipt, signer = _scenario_evidence(tmp_path, rule="rule")
    verifier = signer.verifier()
    with pytest.raises(ValueError, match="cluster/failure/rule binding mismatch"):
        run_active_dreaming_reference_core(
            _active(hashlib.sha256(path.read_bytes()).hexdigest()),
            abstracted_rule_by_cluster={0: "different-rule"},
            scenario_execution_receipts={"dream-0": receipt},
            scenario_program_paths={"dream-0": path},
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
        )


def test_active_dreaming_rejects_one_receipt_replayed_across_two_clusters(
    tmp_path: Path,
) -> None:
    failures = (
        FailureEpisode(episode_id="a1", content="a1", embedding=(1.0, 0.0)),
        FailureEpisode(episode_id="a2", content="a2", embedding=(0.99, 0.01)),
        FailureEpisode(episode_id="b1", content="b1", embedding=(-1.0, 0.0)),
        FailureEpisode(episode_id="b2", content="b2", embedding=(-0.99, -0.01)),
    )
    path, receipt, signer = _scenario_evidence(
        tmp_path,
        failure_set_sha256=content_sha256(failures[:2]),
        rule="rule-a",
    )
    payload_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    inputs = ActiveDreamingAdaptationInput(
        episodic_failures=failures,
        semantic_memory_before=(),
        counterfactual_scenarios=(
            CounterfactualScenario(
                scenario_id="dream-0",
                cluster_hint="0",
                executable_payload_sha256=payload_sha256,
            ),
            CounterfactualScenario(
                scenario_id="dream-1",
                cluster_hint="1",
                executable_payload_sha256=payload_sha256,
            ),
        ),
    )
    verifier = signer.verifier()
    with pytest.raises(ValueError, match="cluster/failure/rule binding mismatch"):
        run_active_dreaming_reference_core(
            inputs,
            abstracted_rule_by_cluster={0: "rule-a", 1: "rule-b"},
            scenario_execution_receipts={"dream-0": receipt, "dream-1": receipt},
            scenario_program_paths={"dream-0": path, "dream-1": path},
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
        )


def test_counterfactual_overflow_produces_signed_failure_receipt(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "structure-two-counterfactual-scenario@0.7",
                "scenario_id": "overflow",
                "cluster_id": 0,
                "failure_set_sha256": HASH_A,
                "candidate_rule_sha256": HASH_B,
                "initial_state": {"value": 1e308},
                "instructions": [{"operation": "increment", "key": "value", "value": 1e308}],
                "expected_final_state": {"value": 1e308},
            }
        ),
        encoding="utf-8",
    )
    signer = Ed25519AttestationSigner.generate(key_id="overflow-executor")
    receipt = execute_counterfactual_scenario(path, signer=signer)
    assert receipt.execution_succeeded is False
    assert receipt.exit_code == 1
    assert receipt.failure_reason == "non_finite_numeric_result"
    assert receipt.execution_log[-1].error_code == "non_finite_numeric_result"
    signer.verifier().verify(
        ATTESTATION_DOMAIN,
        attested_execution_payload(receipt),
        receipt.attestation,
    )


def test_counterfactual_program_resource_bounds_are_enforced(tmp_path: Path) -> None:
    payload = {
        "protocol": "structure-two-counterfactual-scenario@0.7",
        "scenario_id": "too-many",
        "cluster_id": 0,
        "failure_set_sha256": HASH_A,
        "candidate_rule_sha256": HASH_B,
        "initial_state": {},
        "instructions": [
            {"operation": "set", "key": "x", "value": 1} for _ in range(MAX_INSTRUCTIONS + 1)
        ],
        "expected_final_state": {"x": 1},
    }
    with pytest.raises(ValidationError, match="at most"):
        CounterfactualScenarioProgram.model_validate(payload)
    oversized = tmp_path / "oversized.json"
    oversized.write_text(" " * (MAX_PROGRAM_BYTES + 1), encoding="utf-8")
    signer = Ed25519AttestationSigner.generate(key_id="bounded-executor")
    with pytest.raises(ValueError, match="file-size bound"):
        execute_counterfactual_scenario(oversized, signer=signer)


def test_counterfactual_runtime_state_growth_produces_signed_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state-growth.json"
    initial = {f"k{index}": index for index in range(MAX_STATE_KEYS)}
    path.write_text(
        json.dumps(
            {
                "protocol": "structure-two-counterfactual-scenario@0.7",
                "scenario_id": "state-growth",
                "cluster_id": 0,
                "failure_set_sha256": HASH_A,
                "candidate_rule_sha256": HASH_B,
                "initial_state": initial,
                "instructions": [{"operation": "set", "key": "overflow-key", "value": 1}],
                "expected_final_state": initial,
            }
        ),
        encoding="utf-8",
    )
    signer = Ed25519AttestationSigner.generate(key_id="state-bound-executor")
    receipt = execute_counterfactual_scenario(path, signer=signer)
    assert receipt.execution_succeeded is False
    assert receipt.failure_reason == "state_key_limit_exceeded"
    signer.verifier().verify(
        ATTESTATION_DOMAIN,
        attested_execution_payload(receipt),
        receipt.attestation,
    )


def test_active_dreaming_old_boolean_assertion_is_rejected() -> None:
    payload = _active(HASH_A).model_dump()
    payload["counterfactual_scenarios"][0]["externally_asserted_execution_success"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ActiveDreamingAdaptationInput.model_validate(payload)


def test_active_dreaming_rejects_a_missing_cluster_scenario() -> None:
    payload = _active(HASH_A).model_dump()
    payload["counterfactual_scenarios"] = [
        {
            "scenario_id": "wrong",
            "cluster_hint": "9",
            "executable_payload_sha256": HASH_A,
        }
    ]
    with pytest.raises(ValueError, match="exactly cover DBSCAN clusters"):
        run_active_dreaming_reference_core(
            ActiveDreamingAdaptationInput.model_validate(payload),
            abstracted_rule_by_cluster={0: "rule"},
            scenario_execution_receipts={},
            scenario_program_paths={},
            trusted_executor_key_id="executor",
            trusted_executor_public_key_sha256=HASH_A,
        )


def test_auto_dreamer_selects_provenance_bound_replacement_set() -> None:
    inputs = AutoDreamerAdaptationInput(
        session_ids=("s1", "s2"),
        typed_memory_bank=(TypedMemory(memory_id="m1", memory_type="episodic", content="old"),),
        provenance_trajectories=(
            ProvenanceTrajectory(
                trajectory_id="t1",
                source_memory_ids=("m1",),
                downstream_reward=1.0,
                counterfactual_masking_utility=0.5,
            ),
        ),
        offline_boundary_sha256=HASH_A,
        replacement_candidates=(
            TypedMemory(
                memory_id="m2",
                memory_type="semantic",
                content="replacement",
                supersedes=("m1",),
            ),
        ),
    )
    result = run_auto_dreamer_reference_core(inputs)
    assert result.output["working_region"] == ("m1",)
    assert result.output["replacement_memory_ids"] == ("m2",)


def test_auto_dreamer_rejects_ghost_provenance_and_supersedes() -> None:
    common = {
        "session_ids": ("s1", "s2"),
        "typed_memory_bank": (
            TypedMemory(memory_id="real", memory_type="episodic", content="old"),
        ),
        "offline_boundary_sha256": HASH_A,
    }
    with pytest.raises(ValidationError, match="unknown frozen memories"):
        AutoDreamerAdaptationInput(
            **common,
            provenance_trajectories=(
                ProvenanceTrajectory(
                    trajectory_id="t1",
                    source_memory_ids=("ghost",),
                    downstream_reward=1.0,
                    counterfactual_masking_utility=0.5,
                ),
            ),
            replacement_candidates=(
                TypedMemory(
                    memory_id="replacement",
                    memory_type="semantic",
                    content="replacement",
                    supersedes=("ghost",),
                ),
            ),
        )


def _trust_transition(operation: str, *, faithful: bool = True) -> TrustMemTransition:
    previous = (
        TrustMemStateItem(memory_id="protected", content="keep"),
        TrustMemStateItem(memory_id="target", content="old"),
    )
    proposed = (
        TrustMemStateItem(memory_id="protected", content="keep"),
        TrustMemStateItem(
            memory_id="target",
            content=f"new-{operation}",
            evidence_ids=("chunk",) if faithful else ("ghost",),
        ),
    )
    return TrustMemTransition(
        transition_id=operation,
        operation=operation,
        chunk_evidence=("chunk",),
        previous_memory_state_sha256=content_sha256(previous),
        proposed_memory_state_sha256=content_sha256(proposed),
        previous_memory_state=previous,
        proposed_memory_state=proposed,
        required_evidence_ids=("chunk",),
        protected_memory_ids=("protected",),
        downstream_task_outcome=1.0,
    )


def test_trustmem_requires_all_operations_and_all_three_verifiers() -> None:
    inputs = TrustMemAdaptationInput(
        candidate_transitions=(
            _trust_transition("WRITE"),
            _trust_transition("REVISE", faithful=False),
            _trust_transition("PRUNE"),
        )
    )
    result = run_trustmem_reference_core(inputs, minimum_verifier_score=0.8)
    assert result.output["accepted_transition_ids"] == ("WRITE", "PRUNE")
    assert {item.event for item in result.transitions} == {
        "coverage_verified",
        "preservation_verified",
        "faithfulness_verified",
    }


def test_trustmem_rejects_noop_and_computes_verifiers_instead_of_trusting_scores() -> None:
    state = (TrustMemStateItem(memory_id="m", content="same"),)
    with pytest.raises(ValidationError, match="must change memory state"):
        TrustMemTransition(
            transition_id="noop",
            operation="WRITE",
            chunk_evidence=("chunk",),
            previous_memory_state_sha256=content_sha256(state),
            proposed_memory_state_sha256=content_sha256(state),
            previous_memory_state=state,
            proposed_memory_state=state,
            required_evidence_ids=("chunk",),
            protected_memory_ids=("m",),
            downstream_task_outcome=1.0,
        )


def test_brainctl_runs_source_trust_two_stage_gate_and_tier_routing() -> None:
    inputs = BrainctlAdaptationInput(
        content="new durable fact",
        candidate_embedding=(1.0, 0.0),
        neighbor_embeddings=((0.0, 1.0),),
        source="human_verified",
        source_trust=1.0,
        category="decision",
        scope="agent:a",
        confidence=0.9,
        recall_rate=0.8,
        arousal_gain=1.0,
        valence_scale=1.0,
        lifecycle_state="new",
    )
    result = run_brainctl_reference_core(inputs)
    assert result.output["write_tier"] == "FULL_EVOLUTION"
    assert tuple(item.event for item in result.transitions) == (
        "source_trust_scored",
        "two_stage_write_gate_executed",
        "memory_tier_routed",
    )


def test_brainctl_rejects_embedding_dimension_mismatch() -> None:
    with pytest.raises(ValidationError, match="dimensions"):
        BrainctlAdaptationInput(
            content="x",
            candidate_embedding=(1.0, 0.0),
            neighbor_embeddings=((1.0,),),
            source="external_doc",
            source_trust=0.5,
            category="other",
            scope="global",
            confidence=0.2,
            recall_rate=0.2,
            arousal_gain=1.0,
            valence_scale=1.0,
            lifecycle_state="new",
        )


def test_brainctl_negative_similarity_matches_official_zero_floor() -> None:
    result = run_brainctl_reference_core(
        BrainctlAdaptationInput(
            content="opposite neighbor",
            candidate_embedding=(1.0, 0.0),
            neighbor_embeddings=((-1.0, 0.0),),
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
    assert result.output["novelty"] == 1.0
    assert result.output["worthiness_score"] == pytest.approx(0.9251, abs=1e-4)


def test_exact_six_arm_bundle_executes_without_escalating_fidelity(tmp_path: Path) -> None:
    scenario_path, scenario_receipt, signer = _scenario_evidence(tmp_path)
    verifier = signer.verifier()
    auto = AutoDreamerAdaptationInput(
        session_ids=("s1", "s2"),
        typed_memory_bank=(TypedMemory(memory_id="m1", memory_type="episodic", content="old"),),
        provenance_trajectories=(
            ProvenanceTrajectory(
                trajectory_id="t1",
                source_memory_ids=("m1",),
                downstream_reward=1.0,
                counterfactual_masking_utility=0.5,
            ),
        ),
        offline_boundary_sha256=HASH_A,
        replacement_candidates=(
            TypedMemory(
                memory_id="m2",
                memory_type="semantic",
                content="replacement",
                supersedes=("m1",),
            ),
        ),
    )
    bundle = CompleteExternalAdaptationInputsV06(
        corrected_amg=AMGAdaptationInput(
            events=(
                _amg_event("e1", actor_a=0.9, actor_b=0.1),
                _amg_event("e2", actor_a=0.8, actor_b=0.2),
            ),
            hierarchy_edges=(("e1", "e2"),),
            cross_event_constraints=(
                AMGCrossEventConstraint(
                    kind="same_responsible_actor",
                    left_event_id="e1",
                    right_event_id="e2",
                ),
            ),
        ),
        o_star_matched=_o_star(),
        active_dreaming_matched=_active(hashlib.sha256(scenario_path.read_bytes()).hexdigest()),
        auto_dreamer_matched=auto,
        trustmem_matched=TrustMemAdaptationInput(
            candidate_transitions=(
                _trust_transition("WRITE"),
                _trust_transition("REVISE"),
                _trust_transition("PRUNE"),
            )
        ),
        brainctl_matched=BrainctlAdaptationInput(
            content="new durable fact",
            candidate_embedding=(1.0, 0.0),
            neighbor_embeddings=((0.0, 1.0),),
            source="human_verified",
            source_trust=1.0,
            category="decision",
            scope="agent:a",
            confidence=0.9,
            recall_rate=0.8,
            arousal_gain=1.0,
            valence_scale=1.0,
            lifecycle_state="new",
        ),
    )
    execution_signer = Ed25519AttestationSigner.generate(key_id="six-arm-executor")
    source_hashes = {arm: content_sha256({"source": arm}) for arm in CANONICAL_SIX_ARMS}
    implementation_hashes = {
        arm: content_sha256({"implementation": arm}) for arm in CANONICAL_SIX_ARMS
    }
    result_paths = {arm: tmp_path / f"{arm}-result.json" for arm in CANONICAL_SIX_ARMS}
    receipt_path = tmp_path / "dream-0-receipt.json"
    receipt_path.write_text(json.dumps(scenario_receipt.model_dump(mode="json")), encoding="utf-8")
    input_bundle_path = tmp_path / "six-arm-input-bundle.json"
    input_bundle_path.write_text(json.dumps(bundle.model_dump(mode="json")), encoding="utf-8")
    input_bundle_file_sha256 = hashlib.sha256(input_bundle_path.read_bytes()).hexdigest()
    report = run_six_arm_reference_execution_v0_7(
        bundle,
        input_bundle_artifact_path=input_bundle_path,
        o_star_target_id="keys",
        o_star_config=OStarReferenceConfig(
            initial_pseudocount_mass=10.0,
            hit_weight=3.0,
            miss_weight=2.0,
            leak_rate=0.2,
        ),
        active_rule_by_cluster={0: "rule"},
        active_scenario_execution_receipts={"dream-0": scenario_receipt},
        active_scenario_program_paths={"dream-0": scenario_path},
        arm_result_artifact_paths_by_arm=result_paths,
        active_scenario_receipt_paths={"dream-0": receipt_path},
        trusted_scenario_executor_key_id=verifier.key_id,
        trusted_scenario_executor_public_key_sha256=verifier.public_key_sha256,
        source_artifact_sha256_by_arm=source_hashes,
        implementation_bundle_sha256_by_arm=implementation_hashes,
        executor=execution_signer,
    )
    assert tuple(row["arm"] for row in report["arm_results"]) == CANONICAL_SIX_ARMS
    assert report["all_six_reference_cores_executed"] is True
    assert report["active_scenario_execution_receipts_verified"] is True
    assert report["component_parity_passed"] is False
    assert report["external_fidelity_gate_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False
    verified = verify_six_arm_reference_execution_v0_7(
        report,
        expected_input_bundle_sha256=input_bundle_file_sha256,
        input_bundle_artifact_path=input_bundle_path,
        expected_source_artifact_sha256_by_arm=source_hashes,
        expected_implementation_bundle_sha256_by_arm=implementation_hashes,
        arm_result_artifact_paths_by_arm=result_paths,
        active_scenario_receipt_paths={"dream-0": receipt_path},
        active_scenario_program_paths={"dream-0": scenario_path},
        trusted_executor=execution_signer.verifier(),
        trusted_scenario_executor=verifier,
    )
    assert verified == report

    forged_report = deepcopy(report)
    forged_result_path = result_paths["corrected_amg"]
    forged_result = json.loads(forged_result_path.read_text(encoding="utf-8"))
    forged_result.pop("content_sha256")
    forged_result["claim_boundary"] = "attacker-selected result"
    forged_result_content_sha256 = content_sha256(forged_result)
    forged_result["content_sha256"] = forged_result_content_sha256
    forged_result_path.write_text(json.dumps(forged_result), encoding="utf-8")
    forged_row = next(row for row in forged_report["arm_results"] if row["arm"] == "corrected_amg")
    forged_row["result_content_sha256"] = forged_result_content_sha256
    forged_row["result_artifact_file_sha256"] = hashlib.sha256(
        forged_result_path.read_bytes()
    ).hexdigest()
    forged_report.pop("content_sha256")
    forged_report.pop("attestation")
    forged_report["attestation"] = execution_signer.sign(
        SIX_ARM_ATTESTATION_DOMAIN, forged_report
    ).model_dump(mode="json")
    forged_report["content_sha256"] = content_sha256(forged_report)
    with pytest.raises(ValueError, match="deterministic re-execution"):
        verify_six_arm_reference_execution_v0_7(
            forged_report,
            expected_input_bundle_sha256=input_bundle_file_sha256,
            input_bundle_artifact_path=input_bundle_path,
            expected_source_artifact_sha256_by_arm=source_hashes,
            expected_implementation_bundle_sha256_by_arm=implementation_hashes,
            arm_result_artifact_paths_by_arm=result_paths,
            active_scenario_receipt_paths={"dream-0": receipt_path},
            active_scenario_program_paths={"dream-0": scenario_path},
            trusted_executor=execution_signer.verifier(),
            trusted_scenario_executor=verifier,
        )


def test_six_arm_reference_execution_rejects_self_hashed_minimal_claim(
    tmp_path: Path,
) -> None:
    fake: dict[str, object] = {
        "protocol": "structure-two-six-arm-reference-execution@0.7",
        "all_six_reference_cores_executed": True,
    }
    fake["content_sha256"] = content_sha256(fake)
    executor = Ed25519AttestationSigner.generate(key_id="trusted-six-arm-executor")
    with pytest.raises(ValueError, match="lacks an executor signature"):
        verify_six_arm_reference_execution_v0_7(
            fake,
            expected_input_bundle_sha256=HASH_A,
            input_bundle_artifact_path=tmp_path / "unused.json",
            expected_source_artifact_sha256_by_arm={arm: HASH_A for arm in CANONICAL_SIX_ARMS},
            expected_implementation_bundle_sha256_by_arm={
                arm: HASH_B for arm in CANONICAL_SIX_ARMS
            },
            arm_result_artifact_paths_by_arm={},
            active_scenario_receipt_paths={},
            active_scenario_program_paths={},
            trusted_executor=executor.verifier(),
            trusted_scenario_executor=executor.verifier(),
        )
