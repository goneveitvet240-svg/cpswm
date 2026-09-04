from __future__ import annotations

# ruff: noqa: E501 -- the standalone frozen fixture source is hashed verbatim.
import json
import subprocess
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import test_structure_two_canonical_episode_executor_v0_9 as canonical_test
from pydantic import ValidationError
from test_structure_two_external_verification_freeze_v1_0 import Ceremony as FreezeCeremony

from cpswm.system.attestation import (
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations import structure_two_isolation_v0_9 as isolation_v0_9
from cpswm.system.evaluation_operations import structure_two_sealed_dual_gate_b_v1_0 as formal
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    AGGREGATE_ATTESTATION_DOMAIN,
    CanonicalEpisodeTaskV09,
    CanonicalPerEpisodeExecutionArtifactV09,
    IsolatedTaskRunArtifactsV09,
    MechanismStepRecordV09,
    initial_mechanism_state_sha256_v0_9,
    make_isolated_candidate_output_v0_9,
    make_isolated_episode_execution_receipt_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    ACTION_SCHEMA_ID,
    ACTION_SUPPORT,
    ACTION_SUPPORT_MANIFEST_SHA256,
    BELIEF_SCHEMA_ID,
    BELIEF_SUPPORT,
    BELIEF_SUPPORT_MANIFEST_SHA256,
    CANONICAL_COMPONENT_IDS,
    CANONICAL_MECHANISM_EVENTS,
    EXPECTED_ARMS,
    canonical_frozen_protocol_payload_v0_7,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v0_9 import (
    OpeningConsumptionLedgerHeadV09,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    make_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
    ExternalVerificationFreezeV10,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    ATTESTATION_DOMAIN as ISOLATION_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    IsolationExecutionReceiptV09,
    IsolationResourceLimitsV09,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    ATTESTATION_DOMAIN as OPENING_DOMAIN,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    SealedGateBOpeningV09,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

pytest_plugins = ("test_structure_two_canonical_episode_executor_v0_9",)


_REAL_DUAL_ENTRYPOINT_SOURCE = r"""import argparse
import hashlib
import json
from pathlib import Path

EVENTS = {
    "corrected_amg": ["global_multi_event_map_inference"],
    "o_star_matched": ["dirichlet_hit_or_miss_update", "stay_leak_transition", "cost_aware_search"],
    "sequential_no_consolidation": ["typed_particle_update_without_consolidation"],
    "active_dreaming_matched": ["failure_clustered", "counterfactual_scenario_executed_with_attested_receipt", "semantic_rule_committed_after_attested_execution"],
    "auto_dreamer_matched": ["offline_region_selected", "provenance_trajectory_inspected", "replacement_set_committed"],
    "trustmem_matched": ["coverage_verified", "preservation_verified", "faithfulness_verified"],
    "brainctl_matched": ["source_trust_scored", "two_stage_write_gate_executed", "memory_tier_routed"],
    "care_no_action_regret": ["confidence_only_reversible_escrow"],
    "care_wm": ["future_action_regret_decision", "reversible_ledger_update"],
    "full_rerun": ["complete_visible_history_recomputed"],
}
COMPONENTS = {
    "corrected_amg": "corrected_amg:reference-core@0.7",
    "o_star_matched": "o_star_matched:reference-core@0.7",
    "sequential_no_consolidation": "sequential_no_consolidation:core@0.7",
    "active_dreaming_matched": "active_dreaming_matched:reference-core@0.7",
    "auto_dreamer_matched": "auto_dreamer_matched:reference-core@0.7",
    "trustmem_matched": "trustmem_matched:reference-core@0.7",
    "brainctl_matched": "brainctl_matched:reference-core@0.7",
    "care_no_action_regret": "care_no_action_regret:core@0.7",
    "care_wm": "care_wm:core@0.7",
    "full_rerun": "full_rerun:core@0.7",
}
BELIEF_MANIFEST = "__BELIEF_MANIFEST__"
ACTION_MANIFEST = "__ACTION_MANIFEST__"
CARE_ACTION = "__CARE_ACTION__"
CONTROL_ACTION = "__CONTROL_ACTION__"
OPENING_ESCAPE = __OPENING_ESCAPE_JSON__

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--visible-input", required=True)
parser.add_argument("--canonical-context", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--task-content-sha256", required=True)
parser.add_argument("--instrumented-dual-readout-v1", action="store_true")
parser.add_argument("--external-verification-freeze-content-sha256", required=True)
args = parser.parse_args()
if not args.instrumented_dual_readout_v1:
    raise SystemExit(31)
try:
    Path(OPENING_ESCAPE).read_bytes()
except OSError:
    pass
else:
    raise SystemExit(35)
json.loads(Path(args.visible_input).read_text(encoding="utf-8"))
envelope = json.loads(Path(args.canonical_context).read_text(encoding="utf-8"))
stored = envelope.pop("content_sha256")
if stored != digest(envelope):
    raise SystemExit(32)
if envelope["source_task_content_sha256"] != args.task_content_sha256:
    raise SystemExit(33)
if envelope["external_verification_freeze_content_sha256"] != args.external_verification_freeze_content_sha256:
    raise SystemExit(34)
arm = envelope["arm"]
care = arm == "care_wm"
action = CARE_ACTION if care else CONTROL_ACTION
state = digest({"protocol": "structure-two-mechanism-state-chain@0.9", "task_content_sha256": args.task_content_sha256, "position": "initial"})
steps = []
for index in range(envelope["expected_step_count"]):
    next_state = digest({"task": args.task_content_sha256, "step": index, "input": state, "action": action})
    steps.append({
        "step_index": index,
        "step_id": f"{envelope['episode_id']}:step:{index}",
        "information_set": envelope["expected_information_sets"][index],
        "budget": envelope["expected_budget"],
        "readout_stage": "pre_action_pre_evaluator_truth",
        "evaluator_truth_accessed": False,
        "belief": {
            "schema_id": "structure-two-common-joint-belief-readout@0.7",
            "support_manifest_sha256": BELIEF_MANIFEST,
            "probabilities": ([1.0] + [0.0] * 21600) if care else ([0.0, 1.0] + [0.0] * 21599),
        },
        "action_policy": {
            "schema_id": "structure-two-common-action-policy-readout@0.7",
            "support_manifest_sha256": ACTION_MANIFEST,
            "probabilities": ([1.0] + [0.0] * 38) if care else ([0.0, 1.0] + [0.0] * 37),
        },
        "selected_action": action,
        "action_selection_rule": "deterministic_argmax_lexical_tie_break",
        "mechanism_events": [
            {
                "event": event,
                "component_id": COMPONENTS[arm],
                "input_state_sha256": state,
                "output_state_sha256": next_state,
            }
            for event in EVENTS[arm]
        ],
    })
    state = next_state
output = {
    "protocol": "structure-two-isolated-dual-readout-output@1.0",
    "external_verification_freeze_content_sha256": envelope["external_verification_freeze_content_sha256"],
    "canonical_execution_content_sha256": envelope["canonical_execution_content_sha256"],
    "canonical_execution_id": envelope["canonical_execution_id"],
    "canonical_task_receipt_content_sha256": envelope["canonical_task_receipt_content_sha256"],
    "canonical_isolation_receipt_content_sha256": envelope["canonical_isolation_receipt_content_sha256"],
    "task_index": envelope["task_index"],
    "arm": arm,
    "episode_id": envelope["episode_id"],
    "instrumented_canonical_rerun": True,
    "pre_action_readouts_emitted_inside_arm_execution": True,
    "steps": steps,
}
output["content_sha256"] = digest(output)
Path(args.output).write_text(canonical(output), encoding="utf-8")
"""


def _install_real_dual_entrypoints(harness: canonical_test._Harness) -> None:
    engine = isolation_v0_9.MACOS_PROBE_PYTHON_PATH.resolve(strict=True)
    source = (
        _REAL_DUAL_ENTRYPOINT_SOURCE.replace("__BELIEF_MANIFEST__", BELIEF_SUPPORT_MANIFEST_SHA256)
        .replace("__ACTION_MANIFEST__", ACTION_SUPPORT_MANIFEST_SHA256)
        .replace("__CARE_ACTION__", ACTION_SUPPORT[0])
        .replace("__CONTROL_ACTION__", ACTION_SUPPORT[1])
        .replace("__OPENING_ESCAPE_JSON__", json.dumps(str(harness.opening_path.resolve())))
    )
    for arm in EXPECTED_ARMS:
        bundle = harness.bundle_paths[arm]
        entrypoint = bundle / "run.py"
        entrypoint.write_text(source, encoding="utf-8")
        manifest_path = bundle / canonical_test.BUNDLE_MANIFEST_FILENAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("content_sha256")
        manifest["entrypoint_sha256"] = canonical_test.artifact_content_sha256_v0_9(entrypoint)
        manifest["command_engine_path"] = str(engine)
        manifest["command_engine_sha256"] = canonical_test.artifact_content_sha256_v0_9(engine)
        manifest_hash = content_sha256(manifest)
        canonical_test._write_json(
            manifest_path,
            {**manifest, "content_sha256": manifest_hash},
        )
        harness.manifest_hashes[arm] = manifest_hash
        harness.bundle_hashes[arm] = canonical_test.artifact_content_sha256_v0_9(bundle)
    frozen = json.loads(harness.frozen_manifest_path.read_text(encoding="utf-8"))
    frozen.pop("content_sha256")
    frozen["arm_implementation_bundle_sha256"] = dict(harness.bundle_hashes)
    canonical_test._write_json(
        harness.frozen_manifest_path,
        {**frozen, "content_sha256": content_sha256(frozen)},
    )


class _DualCapableSourceRunner:
    """Synthetic arm runner; its receipts are not claims of external execution."""

    def __init__(self, signer: Ed25519AttestationSigner) -> None:
        self.signer = signer

    def run(
        self,
        *,
        task: CanonicalEpisodeTaskV09,
        bundle_path: Path,
        entrypoint_path: Path,
        visible_input_path: Path,
        isolation_working_directory: Path,
        isolation_arguments: tuple[str, ...],
    ) -> IsolatedTaskRunArtifactsV09:
        del entrypoint_path
        action = ACTION_SUPPORT[0] if task.arm == "care_wm" else ACTION_SUPPORT[1]
        state = initial_mechanism_state_sha256_v0_9(task)
        steps: list[MechanismStepRecordV09] = []
        for index in range(task.expected_step_count):
            output_state = content_sha256(
                {"task": task.content_sha256, "step": index, "input": state, "action": action}
            )
            steps.append(
                MechanismStepRecordV09(
                    step_index=index,
                    action=action,
                    mechanism_events=CANONICAL_MECHANISM_EVENTS[task.arm],
                    input_state_sha256=state,
                    output_state_sha256=output_state,
                )
            )
            state = output_state
        candidate = make_isolated_candidate_output_v0_9(
            task=task,
            action_sequence=(action,) * task.expected_step_count,
            mechanism_steps=steps,
        )
        output_path = isolation_working_directory / canonical_test.ISOLATION_OUTPUT_RELATIVE_PATH
        canonical_test._write_json(output_path, candidate)
        isolation_payload = canonical_test._make_formal_isolation_receipt(
            task=task,
            bundle_path=bundle_path,
            visible_input_path=visible_input_path,
            working_directory=isolation_working_directory,
            arguments=isolation_arguments,
            signer=self.signer,
        )
        task_payload = make_isolated_episode_execution_receipt_v0_9(
            task=task,
            action_sequence=(action,) * task.expected_step_count,
            mechanism_steps=steps,
            exit_status="succeeded",
            exit_code=0,
            isolation_receipt_content_sha256=str(isolation_payload["content_sha256"]),
            isolated_output_artifact_sha256=(
                canonical_test.artifact_content_sha256_v0_9(output_path)
            ),
            isolated_output_content_sha256=str(candidate["content_sha256"]),
            signer=self.signer,
        )
        return IsolatedTaskRunArtifactsV09(
            episode_execution_receipt=task_payload,
            isolation_execution_receipt=isolation_payload,
        )


class _SyntheticIsolationVerifier:
    """Strict test double; deliberately not evidence of a live sandbox run."""

    def __call__(
        self,
        payload: Mapping[str, Any],
        *,
        trusted_executor: Ed25519AttestationVerifier,
        command_engine_path: Path,
        arguments: Sequence[str],
        code_bundle_path: Path,
        input_artifact_paths: Mapping[str, Path],
        working_directory: Path,
        expected_output_relative_paths: Mapping[str, str | Path],
        timeout_seconds: int,
        resource_limits: IsolationResourceLimitsV09,
    ) -> IsolationExecutionReceiptV09:
        raw = dict(payload)
        stored = raw.pop("content_sha256", None)
        if stored != content_sha256(raw):
            raise ValueError("synthetic isolation content hash mismatch")
        receipt = IsolationExecutionReceiptV09.model_validate(raw)
        trusted_executor.verify(
            ISOLATION_DOMAIN,
            receipt.model_dump(mode="json", exclude={"executor_attestation"}),
            receipt.executor_attestation,
        )
        if receipt.command_engine_path != str(command_engine_path.resolve(strict=True)):
            raise ValueError("synthetic isolation engine substitution")
        if receipt.argv != (receipt.command_engine_path, *tuple(arguments)):
            raise ValueError("synthetic isolation argv substitution")
        if receipt.code_bundle != canonical_test._isolation_binding(
            "code_bundle", code_bundle_path
        ):
            raise ValueError("synthetic isolation bundle substitution")
        expected_inputs = tuple(
            canonical_test._isolation_binding(label, input_artifact_paths[label])
            for label in sorted(input_artifact_paths)
        )
        if receipt.input_artifacts != expected_inputs:
            raise ValueError("synthetic isolation input substitution")
        if receipt.working_directory != str(working_directory.resolve(strict=True)):
            raise ValueError("synthetic isolation workdir substitution")
        expected_outputs = tuple(
            canonical_test._isolation_binding(label, working_directory / relative)
            for label, relative in expected_output_relative_paths.items()
        )
        if receipt.output_artifacts != expected_outputs:
            raise ValueError("synthetic isolation output substitution")
        if receipt.timeout_seconds != timeout_seconds or receipt.resource_limits != resource_limits:
            raise ValueError("synthetic isolation limits substitution")
        return receipt


@dataclass(frozen=True)
class SyntheticDualGateChain:
    freeze_ceremony: FreezeCeremony
    freeze_payload: dict[str, Any]
    freeze: ExternalVerificationFreezeV10
    canonical: CanonicalPerEpisodeExecutionArtifactV09
    opening: SealedGateBOpeningV09
    consumption_head: OpeningConsumptionLedgerHeadV09
    task_receipts: tuple[formal.DualReadoutTaskReceiptV10, ...]
    isolation_inputs: dict[tuple[str, str], formal.DualReadoutIsolationVerificationInputsV10]
    execution_payload: dict[str, Any]
    execution: formal.CanonicalDualReadoutExecutionV10
    formal_payload: dict[str, Any]
    formal_receipt: formal.SealedDualGateBReceiptV10


def _signed_opening(
    freeze: ExternalVerificationFreezeV10,
    canonical: CanonicalPerEpisodeExecutionArtifactV09,
    custodian: Ed25519AttestationSigner,
) -> SealedGateBOpeningV09:
    verifier = custodian.verifier()
    prerequisites = canonical.verified_prerequisites
    unsigned = SealedGateBOpeningV09.model_construct(
        protocol="structure-two-sealed-gate-b-opening@0.9",
        evaluation_set_role="custodian_sealed_confirmatory_gate_b",
        status="OPENED_ONCE_AFTER_PASSED_GATE_A",
        immutable_manifest_sha256=prerequisites.immutable_manifest_sha256,
        producer_run_id=prerequisites.producer_run_id,
        commitment_record_content_sha256="1" * 64,
        gate_a_lifecycle_record_content_sha256="2" * 64,
        gate_a_report_content_sha256=prerequisites.gate_a_report_content_sha256,
        gate_a_passed=True,
        forbidden_seed_namespaces_sha256=(freeze.body.forbidden_seed_namespaces_sha256),
        arm_implementation_bundle_set_sha256="3" * 64,
        sealed_gate_b_commitment_sha256="4" * 64,
        opening_attempt_id=prerequisites.opening_attempt_id,
        ledger_identifier="authority-ledger:synthetic",
        freeze_ledger_sequence=4,
        commitment_ledger_sequence=5,
        gate_a_ledger_sequence=6,
        opening_ledger_sequence=7,
        freeze_completed_at_utc=freeze.body.frozen_at_utc,
        committed_at_utc=freeze.body.frozen_at_utc + timedelta(hours=1),
        gate_a_completed_at_utc=freeze.body.frozen_at_utc + timedelta(hours=2),
        opened_at_utc=freeze.body.frozen_at_utc + timedelta(hours=3),
        commitment_nonce="synthetic-commitment-nonce",
        world_distribution={"synthetic": True},
        world_seeds=(101,),
        trajectory_seeds=(201,),
        observation_seeds=(301,),
        estimator={"synthetic": 1},
        bootstrap_draws=4000,
        custodian_key_id=verifier.key_id,
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
        custodian_attestation=None,
    )
    return unsigned.model_copy(
        update={
            "custodian_attestation": custodian.sign(
                OPENING_DOMAIN,
                attested_payload(unsigned, exclude=frozenset({"custodian_attestation"})),
            )
        }
    )


def _resign_canonical_for_opening(
    canonical: CanonicalPerEpisodeExecutionArtifactV09,
    opening: SealedGateBOpeningV09,
    executor: Ed25519AttestationSigner,
) -> CanonicalPerEpisodeExecutionArtifactV09:
    prerequisites = canonical.verified_prerequisites.model_copy(
        update={"sealed_opening_content_sha256": content_sha256(opening.model_dump(mode="json"))}
    )
    unsigned = canonical.model_copy(
        update={"verified_prerequisites": prerequisites, "attestation": None}
    )
    return unsigned.model_copy(
        update={
            "attestation": executor.sign(
                AGGREGATE_ATTESTATION_DOMAIN,
                attested_payload(unsigned),
            )
        }
    )


def _step(
    source_step: Any,
    arm: str,
    episode_id: str,
    information_set: formal.InformationSetEvidenceV10,
    budget: formal.BudgetEvidenceV10,
) -> formal.DualReadoutStepEvidenceV10:
    care = arm == "care_wm"
    belief_probabilities = (
        (1.0, *([0.0] * (len(BELIEF_SUPPORT) - 1)))
        if care
        else (0.0, 1.0, *([0.0] * (len(BELIEF_SUPPORT) - 2)))
    )
    action_probabilities = (
        (1.0, *([0.0] * (len(ACTION_SUPPORT) - 1)))
        if care
        else (0.0, 1.0, *([0.0] * (len(ACTION_SUPPORT) - 2)))
    )
    return formal.DualReadoutStepEvidenceV10(
        step_index=source_step.step_index,
        step_id=f"{episode_id}:step:{source_step.step_index}",
        information_set=information_set,
        budget=budget,
        belief=formal.DenseDistributionV10(
            schema_id=BELIEF_SCHEMA_ID,
            support_manifest_sha256=BELIEF_SUPPORT_MANIFEST_SHA256,
            probabilities=belief_probabilities,
        ),
        action_policy=formal.DenseDistributionV10(
            schema_id=ACTION_SCHEMA_ID,
            support_manifest_sha256=ACTION_SUPPORT_MANIFEST_SHA256,
            probabilities=action_probabilities,
        ),
        selected_action=ACTION_SUPPORT[0] if care else ACTION_SUPPORT[1],
        mechanism_events=tuple(
            formal.MechanismEventEvidenceV10(
                event=event,
                component_id=CANONICAL_COMPONENT_IDS[arm],
                input_state_sha256=source_step.input_state_sha256,
                output_state_sha256=source_step.output_state_sha256,
            )
            for event in source_step.mechanism_events
        ),
    )


def _dual_isolation_payload(
    *,
    source: Any,
    bundle_path: Path,
    visible_input_path: Path,
    context_path: Path,
    work: Path,
    output_path: Path,
    arguments: tuple[str, ...],
    runner: Ed25519AttestationSigner,
) -> dict[str, Any]:
    base = source.isolation.receipt
    started = datetime(2026, 9, 4, 9, 0, tzinfo=UTC) + timedelta(seconds=source.receipt.task_index)
    unsigned = base.model_copy(
        update={
            "argv": (base.command_engine_path, *arguments),
            "working_directory": str(work.resolve(strict=True)),
            "code_bundle": canonical_test._isolation_binding("code_bundle", bundle_path),
            "input_artifacts": (
                canonical_test._isolation_binding(formal.DUAL_CONTEXT_LABEL, context_path),
                canonical_test._isolation_binding("visible_episode_input", visible_input_path),
            ),
            "expected_output_relative_paths": {
                formal.DUAL_OUTPUT_LABEL: formal.DUAL_OUTPUT_RELATIVE_PATH
            },
            "output_artifacts": (
                canonical_test._isolation_binding(formal.DUAL_OUTPUT_LABEL, output_path),
            ),
            "started_at_utc": started,
            "finished_at_utc": started + timedelta(seconds=1),
            "executor_attestation": None,
            "claim_boundary": "synthetic test receipt; not external execution evidence",
        }
    )
    signed = unsigned.model_copy(
        update={
            "executor_attestation": runner.sign(
                ISOLATION_DOMAIN,
                unsigned.model_dump(mode="json", exclude={"executor_attestation"}),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def build_synthetic_dual_gate_chain(
    tmp_path: Path,
    harness: canonical_test._Harness,
    monkeypatch: pytest.MonkeyPatch,
    *,
    real_isolation: bool = False,
) -> SyntheticDualGateChain:
    """Reusable positive fixture; even its real sandbox run is not external evidence."""

    if real_isolation:
        _install_real_dual_entrypoints(harness)
    canonical_payload = harness.run(_DualCapableSourceRunner(harness.runner_signer))
    canonical = harness.verify(canonical_payload)

    freeze_ceremony = FreezeCeremony(tmp_path / "freeze")
    freeze_ceremony.executor = harness.executor_signer
    freeze_ceremony.canonical_runner = harness.runner_signer
    freeze_ceremony.registry = make_trust_anchor_registry_v0_6(
        role_signers={
            "reviewer": freeze_ceremony.reviewer,
            "executor": freeze_ceremony.executor,
            "custodian": freeze_ceremony.custodian,
        },
        controller_identifiers={
            "reviewer": "synthetic-reviewer",
            "executor": "synthetic-executor",
            "custodian": "synthetic-custodian",
        },
        enrolled_at_utc=datetime(2026, 9, 4, tzinfo=UTC),
        enrollment_authority=freeze_ceremony.authority,
    )
    freeze_payload, freeze = freeze_ceremony.finalize()
    freeze_hash = str(freeze_payload["content_sha256"])

    opening = _signed_opening(freeze, canonical, freeze_ceremony.custodian)
    canonical = _resign_canonical_for_opening(canonical, opening, freeze_ceremony.executor)
    opening_hash = content_sha256(opening.model_dump(mode="json"))
    consumption_head = OpeningConsumptionLedgerHeadV09(
        ledger_identifier=opening.ledger_identifier,
        immutable_manifest_sha256=opening.immutable_manifest_sha256,
        producer_run_id=opening.producer_run_id,
        ledger_sequence=opening.opening_ledger_sequence + 1,
        previous_head_sha256="8" * 64,
        record_content_sha256="9" * 64,
        opening_content_sha256=opening_hash,
        opening_attempt_id=opening.opening_attempt_id,
        consumed_at_utc=opening.opened_at_utc + timedelta(minutes=1),
        consumed_attempt_ids=frozenset({opening.opening_attempt_id}),
    )

    if not real_isolation:
        monkeypatch.setattr(
            formal,
            "verify_isolation_receipt_v0_9",
            _SyntheticIsolationVerifier(),
        )
    canonical_hash = content_sha256(canonical.model_dump(mode="json"))
    task_receipts: list[formal.DualReadoutTaskReceiptV10] = []
    isolation_inputs: dict[tuple[str, str], formal.DualReadoutIsolationVerificationInputsV10] = {}
    isolation_finished_at: list[datetime] = []
    for source in canonical.task_receipts:
        pair = (source.receipt.arm, source.receipt.episode_id)
        work = tmp_path / f"dual-work-{source.receipt.task_index}"
        work.mkdir()
        output_path = work / formal.DUAL_OUTPUT_RELATIVE_PATH
        context_path = tmp_path / f"dual-context-{source.receipt.task_index}.json"
        visible = harness.input_paths[source.receipt.episode_id]
        expected_information_sets = formal.canonical_dual_readout_information_sets_v1_0(
            visible,
            expected_visible_input_artifact_sha256=(
                canonical.episode_input_bindings[
                    canonical.episode_ids.index(source.receipt.episode_id)
                ].input_artifact_sha256
            ),
            expected_step_count=len(source.receipt.mechanism_steps),
        )
        expected_budget = formal.canonical_offline_dual_readout_budget_v1_0(
            isolation_v0_9.DEFAULT_RESOURCE_LIMITS
        )
        context = formal.DualReadoutCanonicalContextV10(
            external_verification_freeze_content_sha256=freeze_hash,
            canonical_execution_content_sha256=canonical_hash,
            canonical_execution_id=canonical.execution_id,
            canonical_task_receipt_content_sha256=source.receipt_content_sha256,
            canonical_isolation_receipt_content_sha256=(
                source.isolation.isolation_receipt_content_sha256
            ),
            source_task_content_sha256=source.receipt.task_content_sha256,
            sealed_opening_artifact_sha256=(canonical.sealed_opening_binding.artifact_sha256),
            task_index=source.receipt.task_index,
            arm=source.receipt.arm,
            episode_id=source.receipt.episode_id,
            expected_step_count=len(source.receipt.mechanism_steps),
            expected_information_sets=expected_information_sets,
            expected_budget=expected_budget,
        )
        context_payload = context.model_dump(mode="json")
        context_payload["content_sha256"] = content_sha256(context_payload)
        context_path.write_bytes(canonical_json(context_payload).encode("utf-8"))
        output = formal.DualReadoutTaskOutputV10(
            external_verification_freeze_content_sha256=freeze_hash,
            canonical_execution_content_sha256=canonical_hash,
            canonical_execution_id=canonical.execution_id,
            canonical_task_receipt_content_sha256=source.receipt_content_sha256,
            canonical_isolation_receipt_content_sha256=(
                source.isolation.isolation_receipt_content_sha256
            ),
            task_index=source.receipt.task_index,
            arm=source.receipt.arm,
            episode_id=source.receipt.episode_id,
            instrumented_canonical_rerun=True,
            pre_action_readouts_emitted_inside_arm_execution=True,
            steps=tuple(
                _step(
                    step,
                    source.receipt.arm,
                    source.receipt.episode_id,
                    information_set,
                    expected_budget,
                )
                for step, information_set in zip(
                    source.receipt.mechanism_steps,
                    expected_information_sets,
                    strict=True,
                )
            ),
        )
        bundle = harness.bundle_paths[source.receipt.arm]
        entrypoint = (
            bundle
            / canonical.arm_bundle_bindings[EXPECTED_ARMS.index(source.receipt.arm)].entrypoint
        ).resolve(strict=True)
        arguments = formal._instrumented_rerun_arguments(
            entrypoint_path=entrypoint,
            visible_input_path=visible.resolve(strict=True),
            canonical_context_path=context_path.resolve(strict=True),
            output_path=work.resolve(strict=True) / formal.DUAL_OUTPUT_RELATIVE_PATH,
            source=source,
            freeze_content_sha256=freeze_hash,
        )
        if real_isolation:
            isolation_payload = isolation_v0_9.run_macos_isolated_execution_v0_9(
                command_engine_path=Path(
                    canonical.arm_bundle_bindings[
                        EXPECTED_ARMS.index(source.receipt.arm)
                    ].command_engine_path
                ),
                arguments=arguments,
                code_bundle_path=bundle,
                input_artifact_paths={
                    formal.DUAL_CONTEXT_LABEL: context_path,
                    "visible_episode_input": visible,
                },
                working_directory=work,
                expected_output_relative_paths={
                    formal.DUAL_OUTPUT_LABEL: formal.DUAL_OUTPUT_RELATIVE_PATH
                },
                executor=freeze_ceremony.canonical_runner,
                timeout_seconds=canonical_test.ISOLATION_TIMEOUT_SECONDS,
            )
            isolation_raw = dict(isolation_payload)
            isolation_raw.pop("content_sha256")
            real_receipt = IsolationExecutionReceiptV09.model_validate(isolation_raw)
            if real_receipt.formal_isolation_verified is not True:
                raise AssertionError(
                    "real isolation failed: "
                    f"exit={real_receipt.exit_code}, "
                    f"stderr_sha256={real_receipt.stderr_sha256}, "
                    f"probes={real_receipt.probe_results}"
                )
            isolation_finished_at.append(real_receipt.finished_at_utc)
        else:
            output_payload = output.model_dump(mode="json")
            output_payload["content_sha256"] = content_sha256(output_payload)
            output_path.write_bytes(canonical_json(output_payload).encode("utf-8"))
            isolation_payload = _dual_isolation_payload(
                source=source,
                bundle_path=bundle,
                visible_input_path=visible,
                context_path=context_path,
                work=work,
                output_path=output_path,
                arguments=arguments,
                runner=freeze_ceremony.canonical_runner,
            )
        inputs = formal.DualReadoutIsolationVerificationInputsV10(
            implementation_bundle_path=bundle,
            visible_input_path=visible,
            canonical_context_path=context_path,
            isolation_working_directory=work,
            output_path=output_path,
            isolation_receipt_payload=isolation_payload,
            timeout_seconds=canonical_test.ISOLATION_TIMEOUT_SECONDS,
        )
        isolation_inputs[pair] = inputs
        prepared = formal.prepare_dual_readout_task_receipt_v1_0(
            external_verification_freeze=freeze,
            external_verification_freeze_content_sha256=freeze_hash,
            canonical_execution=canonical,
            canonical_execution_content_sha256=canonical_hash,
            source=source,
            isolation_inputs=inputs,
        )
        task_receipts.append(
            formal.finalize_dual_readout_task_receipt_v1_0(
                prepared,
                runner_attestation=freeze_ceremony.canonical_runner.sign(
                    formal.TASK_RUNNER_DOMAIN,
                    attested_payload(prepared, exclude=frozenset({"runner_attestation"})),
                ),
            )
        )

    config = canonical_frozen_protocol_payload_v0_7()
    completed_at = (
        max(isolation_finished_at) + timedelta(microseconds=1)
        if isolation_finished_at
        else datetime(2026, 9, 4, 10, tzinfo=UTC)
    )
    prepared_execution = formal.prepare_canonical_dual_readout_execution_v1_0(
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        canonical_execution=canonical,
        sealed_opening=opening,
        opening_consumption_head=consumption_head,
        frozen_v0_7_config=config,
        task_receipts=task_receipts,
        isolation_inputs_by_task=isolation_inputs,
        canonical_execution_ledger_sequence=consumption_head.ledger_sequence + 1,
        canonical_execution_completed_at_utc=completed_at,
        trusted_reviewer=freeze_ceremony.reviewer.verifier(),
        trusted_executor=freeze_ceremony.executor.verifier(),
        trusted_custodian=freeze_ceremony.custodian.verifier(),
        trusted_enrollment_authority=freeze_ceremony.authority.verifier(),
    )
    execution_payload = formal.finalize_canonical_dual_readout_execution_v1_0(
        prepared_execution,
        executor_attestation=freeze_ceremony.executor.sign(
            formal.EXECUTION_EXECUTOR_DOMAIN,
            attested_payload(prepared_execution, exclude=frozenset({"executor_attestation"})),
        ),
    )
    execution = formal.verify_canonical_dual_readout_execution_v1_0(
        execution_payload,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        canonical_execution=canonical,
        sealed_opening=opening,
        opening_consumption_head=consumption_head,
        frozen_v0_7_config=config,
        isolation_inputs_by_task=isolation_inputs,
        trusted_reviewer=freeze_ceremony.reviewer.verifier(),
        trusted_executor=freeze_ceremony.executor.verifier(),
        trusted_custodian=freeze_ceremony.custodian.verifier(),
        trusted_enrollment_authority=freeze_ceremony.authority.verifier(),
    )
    prepared_formal = formal.prepare_sealed_dual_gate_b_receipt_v1_0(
        execution=execution,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        gate_b_ledger_sequence=consumption_head.ledger_sequence + 2,
        gate_b_scored_at_utc=completed_at + timedelta(seconds=1),
    )
    requests = formal.sealed_dual_gate_b_role_signing_requests_v1_0(prepared_formal)
    reviewer_attestation = freeze_ceremony.reviewer.sign(*requests["reviewer"])
    executor_attestation = freeze_ceremony.executor.sign(*requests["executor"])
    custodian_attestation = freeze_ceremony.custodian.sign(*requests["custodian"])
    authority_request = formal.sealed_dual_gate_b_authority_signing_request_v1_0(
        prepared_formal,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
    )
    formal_payload = formal.finalize_sealed_dual_gate_b_receipt_v1_0(
        prepared_formal,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
        authority_attestation=freeze_ceremony.authority.sign(*authority_request),
    )
    receipt = formal.verify_sealed_dual_gate_b_receipt_v1_0(
        formal_payload,
        canonical_dual_readout_execution_payload=execution_payload,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=freeze_hash,
        canonical_execution=canonical,
        sealed_opening=opening,
        opening_consumption_head=consumption_head,
        frozen_v0_7_config=config,
        isolation_inputs_by_task=isolation_inputs,
        trusted_reviewer=freeze_ceremony.reviewer.verifier(),
        trusted_executor=freeze_ceremony.executor.verifier(),
        trusted_custodian=freeze_ceremony.custodian.verifier(),
        trusted_enrollment_authority=freeze_ceremony.authority.verifier(),
        verification_time_utc=completed_at + timedelta(seconds=2),
    )
    return SyntheticDualGateChain(
        freeze_ceremony=freeze_ceremony,
        freeze_payload=freeze_payload,
        freeze=freeze,
        canonical=canonical,
        opening=opening,
        consumption_head=consumption_head,
        task_receipts=tuple(task_receipts),
        isolation_inputs=isolation_inputs,
        execution_payload=execution_payload,
        execution=execution,
        formal_payload=formal_payload,
        formal_receipt=receipt,
    )


@pytest.fixture
def synthetic_chain(
    tmp_path: Path,
    harness: canonical_test._Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticDualGateChain:
    return build_synthetic_dual_gate_chain(tmp_path, harness, monkeypatch)


def build_real_isolated_dual_gate_chain(
    tmp_path: Path,
    harness: canonical_test._Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticDualGateChain:
    """Run the test arms under the real macOS sandbox; still not external evidence."""

    if not isolation_v0_9.MACOS_SANDBOX_EXEC_PATH.is_file():
        pytest.skip("requires the fixed macOS sandbox-exec binary")
    if not isolation_v0_9.MACOS_PROBE_PYTHON_PATH.is_file():
        pytest.skip("requires the fixed macOS probe Python binary")
    capability = subprocess.run(
        (
            str(isolation_v0_9.MACOS_SANDBOX_EXEC_PATH),
            "-p",
            "(version 1) (allow default)",
            "/usr/bin/true",
        ),
        check=False,
        capture_output=True,
        timeout=5,
    )
    if capability.returncode != 0:
        pytest.skip("outer test environment forbids nested macOS sandbox-exec")
    return build_synthetic_dual_gate_chain(
        tmp_path,
        harness,
        monkeypatch,
        real_isolation=True,
    )


def test_synthetic_v0_7_chain_is_historical_and_cannot_authorize(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    receipt = synthetic_chain.formal_receipt
    assert receipt.status == "HISTORICAL_V0_7_RECEIPT_INVALIDATED"
    assert receipt.protocol_invalidated is True
    assert receipt.formal_gate_b_passed is False
    assert receipt.seven_operator_ablation_authorized is False
    assert receipt.belief_gate_passed is True
    assert receipt.action_gate_passed is True
    assert receipt.mechanism_gate_passed is True
    assert receipt.external_method_efficacy_comparison_allowed is False
    assert receipt.gate_b_ledger_sequence == (synthetic_chain.consumption_head.ledger_sequence + 2)
    episode_ids = tuple(f"sealed-episode-{index:02d}" for index in range(72))
    expanded_rows = tuple(
        next(row for row in synthetic_chain.task_receipts if row.arm == arm).model_copy(
            update={"task_index": task_index, "episode_id": episode_id}
        )
        for task_index, (arm, episode_id) in enumerate(
            (arm, episode_id) for arm in EXPECTED_ARMS for episode_id in episode_ids
        )
    )
    expanded_fields = {
        name: getattr(synthetic_chain.execution, name)
        for name in type(synthetic_chain.execution).model_fields
        if name not in {"episode_ids", "task_receipts"}
    }
    formal.CanonicalDualReadoutExecutionV10(
        **expanded_fields,
        episode_ids=episode_ids,
        task_receipts=expanded_rows,
    )
    with pytest.raises(ValidationError, match="coverage/order is incomplete"):
        formal.CanonicalDualReadoutExecutionV10(
            **expanded_fields,
            episode_ids=episode_ids,
            task_receipts=expanded_rows[:-1],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "FORMAL_SEALED_DUAL_GATE_B_PASSED"),
        ("protocol_invalidated", False),
        ("formal_gate_b_passed", True),
        ("seven_operator_ablation_authorized", True),
    ),
)
def test_v0_7_historical_receipt_rejects_positive_flag_substitution(
    synthetic_chain: SyntheticDualGateChain,
    field: str,
    value: object,
) -> None:
    forged = synthetic_chain.formal_receipt.model_dump(mode="python")
    forged[field] = value
    with pytest.raises(ValidationError):
        formal.SealedDualGateBReceiptV10.model_validate(forged)


def test_real_sandbox_ten_arm_receipts_bind_full_support_and_deny_opening_bytes(
    tmp_path: Path,
    harness: canonical_test._Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = build_real_isolated_dual_gate_chain(tmp_path, harness, monkeypatch)

    assert len(chain.task_receipts) == len(EXPECTED_ARMS) * len(chain.canonical.episode_ids)
    assert chain.formal_receipt.protocol_invalidated is True
    assert chain.formal_receipt.formal_gate_b_passed is False
    assert chain.formal_receipt.seven_operator_ablation_authorized is False
    first_size: int | None = None
    first_elapsed: float | None = None
    for inputs in chain.isolation_inputs.values():
        raw = dict(inputs.isolation_receipt_payload)
        raw.pop("content_sha256")
        isolation_receipt = IsolationExecutionReceiptV09.model_validate(raw)
        assert isolation_receipt.formal_isolation_verified is True
        assert tuple(item.label for item in isolation_receipt.input_artifacts) == (
            formal.DUAL_CONTEXT_LABEL,
            "visible_episode_input",
        )
        assert all("opening" not in item.label for item in isolation_receipt.input_artifacts)
        output_size = inputs.output_path.stat().st_size
        assert output_size > 100_000
        if first_size is None:
            first_size = output_size
            first_elapsed = (
                isolation_receipt.finished_at_utc - isolation_receipt.started_at_utc
            ).total_seconds()
    print(f"full-support task bytes={first_size}, isolated elapsed seconds={first_elapsed}")


def test_dense_distribution_uses_frozen_manifest_and_full_explicit_vector() -> None:
    probabilities = (1.0, *([0.0] * (len(BELIEF_SUPPORT) - 1)))
    distribution = formal.DenseDistributionV10(
        schema_id=BELIEF_SCHEMA_ID,
        support_manifest_sha256=BELIEF_SUPPORT_MANIFEST_SHA256,
        probabilities=probabilities,
    )

    assert "support" not in distribution.model_dump(mode="json")
    assert distribution.as_v0_7().support == BELIEF_SUPPORT
    with pytest.raises(ValidationError):
        formal.DenseDistributionV10(
            schema_id=BELIEF_SCHEMA_ID,
            support_manifest_sha256="f" * 64,
            probabilities=probabilities,
        )
    with pytest.raises(ValidationError):
        formal.DenseDistributionV10(
            schema_id=BELIEF_SCHEMA_ID,
            support_manifest_sha256=BELIEF_SUPPORT_MANIFEST_SHA256,
            probabilities=probabilities[:-1],
        )


def test_post_truth_metadata_and_v0_6_step_substitutions_are_rejected() -> None:
    base = {
        "step_index": 0,
        "step_id": "episode:step:0",
        "information_set": {
            "visible_input_sha256": "1" * 64,
            "visible_history_sha256": "2" * 64,
            "observation_policy_sha256": "3" * 64,
        },
        "budget": {
            "compute_unit_limit": 1,
            "active_observation_limit": 1,
            "physical_verification_limit": 1,
            "action_cost_limit": 1.0,
            "privacy_cost_limit": 1.0,
        },
        "readout_stage": "post_evaluator_truth",
        "evaluator_truth_accessed": True,
        "belief": {"schema_id": BELIEF_SCHEMA_ID, "support": [], "probabilities": []},
        "action_policy": {"schema_id": ACTION_SCHEMA_ID, "support": [], "probabilities": []},
        "selected_action": "legacy-action",
        "mechanism_events": [],
        "metadata": {"renamed": True},
        "protocol": "structure-two-stratified-mechanism-action-gate-b@0.6",
    }
    with pytest.raises(ValidationError):
        formal.DualReadoutStepEvidenceV10.model_validate(base)


def test_raw_aggregate_substitution_is_rejected(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    forged = deepcopy(synthetic_chain.execution_payload)
    forged["task_receipts"][0]["dual_readout_output_content_sha256"] = "f" * 64
    forged["content_sha256"] = content_sha256(
        {key: value for key, value in forged.items() if key != "content_sha256"}
    )
    chain = synthetic_chain
    with pytest.raises((ValueError, AttestationError)):
        formal.verify_canonical_dual_readout_execution_v1_0(
            forged,
            external_verification_freeze=chain.freeze,
            external_verification_freeze_content_sha256=str(chain.freeze_payload["content_sha256"]),
            canonical_execution=chain.canonical,
            sealed_opening=chain.opening,
            opening_consumption_head=chain.consumption_head,
            frozen_v0_7_config=canonical_frozen_protocol_payload_v0_7(),
            isolation_inputs_by_task=chain.isolation_inputs,
            trusted_reviewer=chain.freeze_ceremony.reviewer.verifier(),
            trusted_executor=chain.freeze_ceremony.executor.verifier(),
            trusted_custodian=chain.freeze_ceremony.custodian.verifier(),
            trusted_enrollment_authority=chain.freeze_ceremony.authority.verifier(),
        )


def test_forged_complete_unregistered_runner_is_rejected(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    attacker = Ed25519AttestationSigner.generate(key_id="unregistered-dual-runner")
    attacker_verifier = attacker.verifier()
    original = chain.task_receipts[0]
    attacker_binding = original.runner.model_copy(
        update={
            "key_id": attacker_verifier.key_id,
            "public_key_base64": attacker_verifier.public_key_base64,
            "public_key_sha256": attacker_verifier.public_key_sha256,
        }
    )
    unsigned_task = original.model_copy(
        update={"runner": attacker_binding, "runner_attestation": None}
    )
    forged_task = unsigned_task.model_copy(
        update={
            "runner_attestation": attacker.sign(
                formal.TASK_RUNNER_DOMAIN,
                attested_payload(
                    unsigned_task,
                    exclude=frozenset({"runner_attestation"}),
                ),
            )
        }
    )
    unsigned_execution = chain.execution.model_copy(
        update={
            "task_receipts": (forged_task, *chain.task_receipts[1:]),
            "executor_attestation": None,
        }
    )
    signed_execution = unsigned_execution.model_copy(
        update={
            "executor_attestation": chain.freeze_ceremony.executor.sign(
                formal.EXECUTION_EXECUTOR_DOMAIN,
                attested_payload(
                    unsigned_execution,
                    exclude=frozenset({"executor_attestation"}),
                ),
            )
        }
    )
    forged_payload = signed_execution.model_dump(mode="json")
    forged_payload["content_sha256"] = content_sha256(forged_payload)

    with pytest.raises(AttestationError, match="unregistered runner"):
        formal.verify_canonical_dual_readout_execution_v1_0(
            forged_payload,
            external_verification_freeze=chain.freeze,
            external_verification_freeze_content_sha256=str(chain.freeze_payload["content_sha256"]),
            canonical_execution=chain.canonical,
            sealed_opening=chain.opening,
            opening_consumption_head=chain.consumption_head,
            frozen_v0_7_config=canonical_frozen_protocol_payload_v0_7(),
            isolation_inputs_by_task=chain.isolation_inputs,
            trusted_reviewer=chain.freeze_ceremony.reviewer.verifier(),
            trusted_executor=chain.freeze_ceremony.executor.verifier(),
            trusted_custodian=chain.freeze_ceremony.custodian.verifier(),
            trusted_enrollment_authority=chain.freeze_ceremony.authority.verifier(),
        )


def test_stale_consumption_head_and_unregistered_role_are_rejected(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    stale = replace(
        chain.consumption_head,
        opening_attempt_id="different-opening-0001",
    )
    attacker = Ed25519AttestationSigner.generate(key_id="attacker-reviewer")
    common = {
        "external_verification_freeze": chain.freeze,
        "external_verification_freeze_content_sha256": str(chain.freeze_payload["content_sha256"]),
        "canonical_execution": chain.canonical,
        "sealed_opening": chain.opening,
        "frozen_v0_7_config": canonical_frozen_protocol_payload_v0_7(),
        "task_receipts": chain.task_receipts,
        "isolation_inputs_by_task": chain.isolation_inputs,
        "canonical_execution_ledger_sequence": chain.consumption_head.ledger_sequence + 1,
        "canonical_execution_completed_at_utc": datetime(2026, 9, 4, 10, tzinfo=UTC),
        "trusted_executor": chain.freeze_ceremony.executor.verifier(),
        "trusted_custodian": chain.freeze_ceremony.custodian.verifier(),
        "trusted_enrollment_authority": chain.freeze_ceremony.authority.verifier(),
    }
    with pytest.raises(ValueError, match="stale, forked, or cross-opening"):
        formal.prepare_canonical_dual_readout_execution_v1_0(
            **common,
            opening_consumption_head=stale,
            trusted_reviewer=chain.freeze_ceremony.reviewer.verifier(),
        )
    with pytest.raises(AttestationError, match="outside the frozen trust registry"):
        formal.prepare_canonical_dual_readout_execution_v1_0(
            **common,
            opening_consumption_head=chain.consumption_head,
            trusted_reviewer=attacker.verifier(),
        )
    legacy_config = deepcopy(canonical_frozen_protocol_payload_v0_7())
    legacy_config["protocol"] = "structure-two-stratified-mechanism-action-gate-b@0.6"
    with pytest.raises(ValueError):
        formal.prepare_canonical_dual_readout_execution_v1_0(
            **{**common, "frozen_v0_7_config": legacy_config},
            opening_consumption_head=chain.consumption_head,
            trusted_reviewer=chain.freeze_ceremony.reviewer.verifier(),
        )


def test_noncanonical_output_bytes_and_isolation_output_substitution_are_rejected(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    pair = next(iter(chain.isolation_inputs))
    inputs = chain.isolation_inputs[pair]
    decoded = json.loads(inputs.output_path.read_bytes())
    inputs.output_path.write_text(json.dumps(decoded, indent=2), encoding="utf-8")
    source = next(
        row
        for row in chain.canonical.task_receipts
        if (row.receipt.arm, row.receipt.episode_id) == pair
    )
    with pytest.raises(ValueError, match="bytes are noncanonical"):
        formal.prepare_dual_readout_task_receipt_v1_0(
            external_verification_freeze=chain.freeze,
            external_verification_freeze_content_sha256=str(chain.freeze_payload["content_sha256"]),
            canonical_execution=chain.canonical,
            canonical_execution_content_sha256=content_sha256(
                chain.canonical.model_dump(mode="json")
            ),
            source=source,
            isolation_inputs=inputs,
        )


def test_common_lies_about_information_prefix_or_budget_are_rejected(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    pair = next(iter(chain.isolation_inputs))
    original_inputs = chain.isolation_inputs[pair]
    source = next(
        row
        for row in chain.canonical.task_receipts
        if (row.receipt.arm, row.receipt.episode_id) == pair
    )
    original_context = original_inputs.canonical_context_path.read_bytes()
    original_output = original_inputs.output_path.read_bytes()
    bundle = original_inputs.implementation_bundle_path
    entrypoint = (
        bundle
        / chain.canonical.arm_bundle_bindings[EXPECTED_ARMS.index(source.receipt.arm)].entrypoint
    ).resolve(strict=True)
    arguments = formal._instrumented_rerun_arguments(
        entrypoint_path=entrypoint,
        visible_input_path=original_inputs.visible_input_path.resolve(strict=True),
        canonical_context_path=original_inputs.canonical_context_path.resolve(strict=True),
        output_path=original_inputs.output_path.resolve(strict=True),
        source=source,
        freeze_content_sha256=str(chain.freeze_payload["content_sha256"]),
    )

    for attack in ("same-false-history", "same-false-budget"):
        context = json.loads(original_context)
        context.pop("content_sha256")
        output = json.loads(original_output)
        output.pop("content_sha256")
        if attack == "same-false-history":
            for information_set in context["expected_information_sets"]:
                information_set["visible_history_sha256"] = "a" * 64
            for step in output["steps"]:
                step["information_set"]["visible_history_sha256"] = "a" * 64
        else:
            context["expected_budget"]["compute_unit_limit"] += 1
            for step in output["steps"]:
                step["budget"]["compute_unit_limit"] += 1
        context["content_sha256"] = content_sha256(context)
        output["content_sha256"] = content_sha256(output)
        original_inputs.canonical_context_path.write_bytes(canonical_json(context).encode("utf-8"))
        original_inputs.output_path.write_bytes(canonical_json(output).encode("utf-8"))
        isolation_payload = _dual_isolation_payload(
            source=source,
            bundle_path=bundle,
            visible_input_path=original_inputs.visible_input_path,
            context_path=original_inputs.canonical_context_path,
            work=original_inputs.isolation_working_directory,
            output_path=original_inputs.output_path,
            arguments=arguments,
            runner=chain.freeze_ceremony.canonical_runner,
        )
        forged_inputs = replace(
            original_inputs,
            isolation_receipt_payload=isolation_payload,
        )
        with pytest.raises(ValueError, match="canonical context is stale"):
            formal.prepare_dual_readout_task_receipt_v1_0(
                external_verification_freeze=chain.freeze,
                external_verification_freeze_content_sha256=str(
                    chain.freeze_payload["content_sha256"]
                ),
                canonical_execution=chain.canonical,
                canonical_execution_content_sha256=content_sha256(
                    chain.canonical.model_dump(mode="json")
                ),
                source=source,
                isolation_inputs=forged_inputs,
            )
        original_inputs.canonical_context_path.write_bytes(original_context)
        original_inputs.output_path.write_bytes(original_output)


def test_finalizer_rejects_wrong_role_or_authority_signature(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    prepared = chain.formal_receipt.model_copy(
        update={
            "reviewer_attestation": None,
            "executor_attestation": None,
            "custodian_attestation": None,
            "authority_attestation": None,
        }
    )
    requests = formal.sealed_dual_gate_b_role_signing_requests_v1_0(prepared)
    reviewer = chain.freeze_ceremony.reviewer.sign(*requests["reviewer"])
    executor = chain.freeze_ceremony.executor.sign(*requests["executor"])
    custodian = chain.freeze_ceremony.custodian.sign(*requests["custodian"])
    attacker = Ed25519AttestationSigner.generate(key_id="forged-formal-authority")

    with pytest.raises(AttestationError):
        formal.finalize_sealed_dual_gate_b_receipt_v1_0(
            prepared,
            reviewer_attestation=reviewer,
            executor_attestation=reviewer,
            custodian_attestation=custodian,
            authority_attestation=attacker.sign("wrong-domain", {}),
        )

    authority_request = formal.sealed_dual_gate_b_authority_signing_request_v1_0(
        prepared,
        reviewer_attestation=reviewer,
        executor_attestation=executor,
        custodian_attestation=custodian,
    )
    with pytest.raises(AttestationError):
        formal.finalize_sealed_dual_gate_b_receipt_v1_0(
            prepared,
            reviewer_attestation=reviewer,
            executor_attestation=executor,
            custodian_attestation=custodian,
            authority_attestation=attacker.sign(*authority_request),
        )


def test_standalone_formal_verifier_rejects_future_scoring_time(
    synthetic_chain: SyntheticDualGateChain,
) -> None:
    chain = synthetic_chain
    with pytest.raises(ValueError, match="verifier's future"):
        formal.verify_sealed_dual_gate_b_receipt_v1_0(
            chain.formal_payload,
            canonical_dual_readout_execution_payload=chain.execution_payload,
            external_verification_freeze=chain.freeze,
            external_verification_freeze_content_sha256=str(chain.freeze_payload["content_sha256"]),
            canonical_execution=chain.canonical,
            sealed_opening=chain.opening,
            opening_consumption_head=chain.consumption_head,
            frozen_v0_7_config=canonical_frozen_protocol_payload_v0_7(),
            isolation_inputs_by_task=chain.isolation_inputs,
            trusted_reviewer=chain.freeze_ceremony.reviewer.verifier(),
            trusted_executor=chain.freeze_ceremony.executor.verifier(),
            trusted_custodian=chain.freeze_ceremony.custodian.verifier(),
            trusted_enrollment_authority=chain.freeze_ceremony.authority.verifier(),
            verification_time_utc=(
                chain.formal_receipt.gate_b_scored_at_utc - timedelta(microseconds=1)
            ),
        )
