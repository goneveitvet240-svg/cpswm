from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations import (
    structure_two_gate_b_v0_8_raw_formal_execution as raw_chain,
)
from cpswm.system.evaluation_operations.structure_two_comparator_typed_dual_gate_b_v0_8 import (
    ACTION_SCHEMA_ID,
    BELIEF_SCHEMA_ID,
    EXPECTED_ARMS,
    DecisionReadout,
    DistributionKind,
    EpisodeDistribution,
    EpisodePublicOntology,
    PublicActionKind,
    ReadoutStage,
    RuntimeAction,
    RuntimeActionMapping,
    RuntimeActionProjection,
    canonical_protocol_payload_v0_8,
    make_runtime_action,
)
from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    PROTOCOL_STATUS as HISTORICAL_V0_7_STATUS,
)
from cpswm.system.reproducibility import canonical_json, content_sha256


def _uuid(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"gate-b-v0.8-raw-chain-test:{label}")


def _uuid_text(label: str) -> str:
    return str(_uuid(label))


def _runtime_for_public(action: str, ontology: EpisodePublicOntology) -> RuntimeAction:
    kind_text, argument = action.split("|", 1)
    argument_name, argument_value = argument.split("=", 1)
    return make_runtime_action(
        kind=PublicActionKind(kind_text),
        target_object_uuid=ontology.target_object_uuid,
        location_uuid=argument_value if argument_name == "location" else None,
        guest_actor_uuid=argument_value if argument_name == "guest" else None,
    )


def _ontology() -> EpisodePublicOntology:
    return EpisodePublicOntology(
        episode_id="episode-confirmatory-001",
        target_object_uuid=_uuid_text("object"),
        owner_actor_uuid=_uuid_text("owner"),
        robot_actor_uuid=_uuid_text("robot"),
        location_uuids=tuple(sorted(_uuid_text(f"location-{index}") for index in range(8))),
        guest_actor_uuids=tuple(sorted((_uuid_text("guest-0"), _uuid_text("guest-1")))),
    )


def _projection(arm: str, ontology: EpisodePublicOntology) -> RuntimeActionProjection:
    return RuntimeActionProjection(
        episode_id=ontology.episode_id,
        arm=arm,
        ontology_manifest_sha256=ontology.manifest_sha256,
        entries=tuple(
            RuntimeActionMapping(
                public_action=action,
                runtime_action=_runtime_for_public(action, ontology),
            )
            for action in ontology.action_support
        ),
    )


def _distribution(
    kind: DistributionKind,
    ontology: EpisodePublicOntology,
    *,
    peak: int,
) -> EpisodeDistribution:
    support = (
        ontology.belief_support if kind is DistributionKind.BELIEF else ontology.action_support
    )
    return EpisodeDistribution(
        kind=kind,
        schema_id=BELIEF_SCHEMA_ID if kind is DistributionKind.BELIEF else ACTION_SCHEMA_ID,
        ontology_manifest_sha256=ontology.manifest_sha256,
        support=support,
        probabilities=tuple(1.0 if index == peak else 0.0 for index in range(len(support))),
    )


def _arm_values(arm: str) -> tuple[int, int, float]:
    if arm in {"care_wm", "full_rerun"}:
        return 0, 0, 0.7
    if arm == "care_no_action_regret":
        return 0, 1, 0.2
    return 1, 1, 0.1


def _identity_fields(
    role: raw_chain.FormalRole,
    signers: dict[raw_chain.FormalRole, Ed25519AttestationSigner],
) -> dict[str, object]:
    verifier = signers[role].verifier()
    return {
        "signer_role": role,
        "signer_authority_id": f"independent-authority:{role.value}",
        "signer_key_id": verifier.key_id,
        "signer_public_key_sha256": verifier.public_key_sha256,
    }


class _Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.t0 = self.now - timedelta(minutes=20)
        self.expiry = self.now + timedelta(minutes=20)
        self.ontology = _ontology()
        self.episode_id = self.ontology.episode_id
        self.run_id = _uuid("run")
        self.registry_id = _uuid("registry")
        self.registry_enrollment = content_sha256(
            {"registry_id": self.registry_id, "custody": "external-test-fixture"}
        )
        self.registry = raw_chain.PersistentReplayRegistryV08(
            path=tmp_path / "gate-b-replay.sqlite3",
            registry_id=self.registry_id,
            enrollment_sha256=self.registry_enrollment,
            initialize=True,
        )
        self.runtime_engine_sha256 = content_sha256({"engine": "test-instrumented-runtime"})
        self.root_signer = Ed25519AttestationSigner.generate(key_id="gate-b-root-test")
        self.signers = {
            role: Ed25519AttestationSigner.generate(key_id=f"gate-b-test:{role.value}")
            for role in raw_chain.ROLE_ORDER
        }
        anchors = tuple(
            raw_chain.TrustAnchorV08(
                role=role,
                authority_id=f"independent-authority:{role.value}",
                key_id=self.signers[role].verifier().key_id,
                public_key_base64=self.signers[role].verifier().public_key_base64,
                public_key_sha256=self.signers[role].verifier().public_key_sha256,
                enrolled_at_utc=self.t0,
            )
            for role in raw_chain.ROLE_ORDER
        )
        root = self.root_signer.verifier()
        unsigned_trust = raw_chain.GateBV08TrustManifest(
            protocol=raw_chain.TRUST_MANIFEST_PROTOCOL_ID,
            manifest_id=_uuid("trust-manifest"),
            issued_at_utc=self.t0 + timedelta(minutes=1),
            expires_at_utc=self.expiry,
            gate_b_protocol_content_sha256=content_sha256(canonical_protocol_payload_v0_8()),
            replay_registry_id=self.registry_id,
            replay_registry_enrollment_sha256=self.registry_enrollment,
            replay_registry_storage_identity_sha256=self.registry.storage_identity_sha256,
            anchors=anchors,
            root_key_id=root.key_id,
            root_public_key_base64=root.public_key_base64,
            root_public_key_sha256=root.public_key_sha256,
        )
        self.trust = raw_chain.sign_trust_manifest_v0_8(
            unsigned_trust,
            root_signer=self.root_signer,
        )
        current = raw_chain.load_raw_formal_chain_policy_v0_8()
        self.policy = current.model_copy(
            update={
                "trust_anchor_status": raw_chain.EnrollmentStatus.ENROLLED,
                "trust_manifest_content_sha256": self.trust.content_sha256,
                "trust_manifest_root_key_id": root.key_id,
                "trust_manifest_root_public_key_base64": root.public_key_base64,
                "trust_manifest_root_public_key_sha256": root.public_key_sha256,
                "replay_registry_status": raw_chain.EnrollmentStatus.ENROLLED,
                "replay_registry_id": self.registry_id,
                "replay_registry_enrollment_sha256": self.registry_enrollment,
                "replay_registry_storage_identity_sha256": (self.registry.storage_identity_sha256),
            }
        )
        self.projections = {arm: _projection(arm, self.ontology) for arm in EXPECTED_ARMS}
        self.task_plan = tuple(
            raw_chain.CanonicalTaskPlanV08(
                task_index=index,
                arm=arm,
                episode_id=self.episode_id,
                expected_step_count=1,
                implementation_bundle_sha256=content_sha256({"frozen-bundle": arm}),
                expected_runtime_engine_sha256=self.runtime_engine_sha256,
            )
            for index, arm in enumerate(EXPECTED_ARMS)
        )
        self.manifest = self._run_manifest()
        self.canonical = self._canonical_verification()
        self.paths: dict[tuple[str, str], Path] = {}
        self.tasks = tuple(
            self._task(index=index, arm=arm, tmp_path=tmp_path)
            for index, arm in enumerate(EXPECTED_ARMS)
        )
        placeholder_review = raw_chain.IndependentReviewReceiptV08(
            protocol=raw_chain.REVIEW_RECEIPT_PROTOCOL_ID,
            **_identity_fields(raw_chain.FormalRole.INDEPENDENT_REVIEWER, self.signers),
            issued_at_utc=self.now - timedelta(minutes=1),
            expires_at_utc=self.expiry,
            nonce=_uuid("review"),
            run_id=self.run_id,
            run_manifest_content_sha256=self.manifest.content_sha256,
            canonical_verification_content_sha256=self.canonical.content_sha256,
            task_evidence_content_sha256=tuple(task.content_sha256 for task in self.tasks),
            diagnostic_report_content_sha256="0" * 64,
            recomputed_outcome="FAIL",
        )
        placeholder_chain = raw_chain.GateBV08RawFormalExecutionChain(
            protocol=raw_chain.PROTOCOL_ID,
            raw_chain_policy_content_sha256=self.policy.content_sha256,
            run_manifest=self.manifest,
            canonical_verification=self.canonical,
            tasks=self.tasks,
            review_receipt=placeholder_review,
        )
        report = raw_chain._derive_diagnostic_report(placeholder_chain)
        unsigned_review = placeholder_review.model_copy(
            update={
                "diagnostic_report_content_sha256": content_sha256(report),
                "recomputed_outcome": (
                    "PASS" if report["diagnostic_typed_relations_passed"] else "FAIL"
                ),
            }
        )
        review = raw_chain.sign_review_receipt_v0_8(
            unsigned_review,
            signer=self.signers[raw_chain.FormalRole.INDEPENDENT_REVIEWER],
        )
        self.chain = placeholder_chain.model_copy(update={"review_receipt": review})

    def _canonical_verification(self) -> raw_chain.CanonicalExecutionVerificationV08:
        tasks: list[raw_chain.CanonicalTaskBindingV08] = []
        for index, arm in enumerate(EXPECTED_ARMS):
            _, action_peak, _ = _arm_values(arm)
            public_action = self.ontology.action_support[action_peak]
            runtime_action = self.projections[arm].inverse(
                public_action,
                ontology=self.ontology,
            )
            tasks.append(
                raw_chain.CanonicalTaskBindingV08(
                    task_index=index,
                    arm=arm,
                    episode_id=self.episode_id,
                    canonical_task_receipt_content_sha256=content_sha256(
                        {"canonical-task": index, "arm": arm}
                    ),
                    implementation_bundle_sha256=content_sha256({"frozen-bundle": arm}),
                    runtime_engine_sha256=self.runtime_engine_sha256,
                    steps=(
                        raw_chain.CanonicalStepBindingV08(
                            step_index=0,
                            runtime_action_id=runtime_action.runtime_action_id,
                            input_state_sha256=content_sha256({"arm": arm, "state": "before"}),
                            output_state_sha256=content_sha256({"arm": arm, "state": "after"}),
                        ),
                    ),
                )
            )
        role = raw_chain.FormalRole.CANONICAL_EXECUTION_VERIFIER
        unsigned = raw_chain.CanonicalExecutionVerificationV08(
            protocol=raw_chain.CANONICAL_VERIFICATION_PROTOCOL_ID,
            **_identity_fields(role, self.signers),
            issued_at_utc=self.t0 + timedelta(minutes=4),
            expires_at_utc=self.expiry,
            nonce=_uuid("canonical-verification"),
            parent_run_manifest_content_sha256=self.manifest.content_sha256,
            canonical_executor_protocol=raw_chain.CANONICAL_EXECUTOR_PROTOCOL_ID,
            canonical_execution_id="canonical-execution-test-0001",
            canonical_execution_artifact_sha256=content_sha256({"canonical-artifact": "raw-bytes"}),
            canonical_execution_content_sha256=content_sha256({"canonical-artifact": "content"}),
            arms=EXPECTED_ARMS,
            episode_ids=(self.episode_id,),
            tasks=tuple(tasks),
        )
        return raw_chain.sign_canonical_verification_v0_8(
            unsigned,
            signer=self.signers[role],
        )

    def _run_manifest(self) -> raw_chain.GateBV08RunManifest:
        role = raw_chain.FormalRole.PREREGISTRATION_CUSTODIAN
        unsigned = raw_chain.GateBV08RunManifest(
            protocol=raw_chain.RUN_MANIFEST_PROTOCOL_ID,
            **_identity_fields(role, self.signers),
            issued_at_utc=self.t0 + timedelta(minutes=3),
            expires_at_utc=self.expiry,
            nonce=_uuid("run-manifest"),
            raw_chain_policy_content_sha256=self.policy.content_sha256,
            run_id=self.run_id,
            gate_b_protocol_content_sha256=content_sha256(canonical_protocol_payload_v0_8()),
            expected_canonical_execution_id="canonical-execution-test-0001",
            arms=EXPECTED_ARMS,
            episodes=(
                raw_chain.EpisodeRegistrationV08(
                    episode_id=self.episode_id,
                    ontology=self.ontology,
                    evaluation_step_index=0,
                    expected_step_count=1,
                    shared_information_set_sha256_by_step=(
                        content_sha256({"episode": self.episode_id, "visible-prefix": 0}),
                    ),
                    shared_decision_id_by_step=(f"{self.episode_id}:decision-0",),
                ),
            ),
            projections=tuple(
                raw_chain.ProjectionRegistrationV08(
                    arm=arm,
                    episode_id=self.episode_id,
                    projection=self.projections[arm],
                )
                for arm in EXPECTED_ARMS
            ),
            canonical_task_plan=self.task_plan,
        )
        return raw_chain.sign_run_manifest_v0_8(unsigned, signer=self.signers[role])

    def _task(self, *, index: int, arm: str, tmp_path: Path) -> raw_chain.RawTaskEvidenceV08:
        source = self.canonical.tasks[index]
        belief_peak, action_peak, utility = _arm_values(arm)
        selected = self.ontology.action_support[action_peak]
        selected_runtime = self.projections[arm].inverse(
            selected,
            ontology=self.ontology,
        )
        readout = DecisionReadout(
            arm=arm,
            episode_id=self.episode_id,
            decision_id=f"{self.episode_id}:decision-0",
            causal_window_id="raw-stepwise-broker",
            information_set_sha256=(
                self.manifest.episodes[0].shared_information_set_sha256_by_step[0]
            ),
            ontology_manifest_sha256=self.ontology.manifest_sha256,
            projection_manifest_sha256=self.projections[arm].manifest_sha256,
            readout_stage=ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
            evaluator_truth_accessed=False,
            readout_event_index=0,
            action_commit_event_index=1,
            belief=_distribution(
                DistributionKind.BELIEF,
                self.ontology,
                peak=belief_peak,
            ),
            action_policy=_distribution(
                DistributionKind.ACTION,
                self.ontology,
                peak=action_peak,
            ),
            selected_public_action=selected,
            selected_runtime_action=selected_runtime,
            realized_utility=utility,
            utility_event_index=3,
        )
        step = raw_chain.RawRuntimeStepV08(
            step_index=0,
            canonical_input_state_sha256=source.steps[0].input_state_sha256,
            canonical_output_state_sha256=source.steps[0].output_state_sha256,
            runtime_state_before_readout_sha256=source.steps[0].input_state_sha256,
            belief_trace_sha256=raw_chain.belief_trace_sha256_v0_8(
                runtime_state_before_readout_sha256=source.steps[0].input_state_sha256,
                readout=readout,
            ),
            action_policy_trace_sha256=raw_chain.action_policy_trace_sha256_v0_8(
                runtime_state_before_readout_sha256=source.steps[0].input_state_sha256,
                readout=readout,
            ),
            evaluator_truth_sha256=content_sha256({"arm": arm, "truth": "sealed"}),
            readout=readout,
        )
        output = raw_chain.RawRuntimeArmEpisodeOutputV08(
            protocol=raw_chain.RAW_OUTPUT_PROTOCOL_ID,
            raw_chain_policy_content_sha256=self.policy.content_sha256,
            run_manifest_content_sha256=self.manifest.content_sha256,
            run_id=self.run_id,
            canonical_execution_id=self.canonical.canonical_execution_id,
            canonical_execution_content_sha256=self.canonical.canonical_execution_content_sha256,
            canonical_task_receipt_content_sha256=source.canonical_task_receipt_content_sha256,
            task_index=index,
            arm=arm,
            episode_id=self.episode_id,
            implementation_bundle_sha256=source.implementation_bundle_sha256,
            runtime_engine_sha256=source.runtime_engine_sha256,
            ontology_manifest_sha256=self.ontology.manifest_sha256,
            projection_manifest_sha256=self.projections[arm].manifest_sha256,
            runtime_mode="instrumented-frozen-bundle-live-state-readout",
            steps=(step,),
        )
        path = tmp_path / f"raw-{index:02d}-{arm}.json"
        encoded = canonical_json(output.model_dump(mode="json")).encode("utf-8")
        path.write_bytes(encoded)
        self.paths[(arm, self.episode_id)] = path
        artifact_sha = content_sha256(output.model_dump(mode="json"))
        assert artifact_sha == output.content_sha256
        runtime_role = raw_chain.FormalRole.RUNTIME_READOUT_EXECUTOR
        unsigned_runtime = raw_chain.RuntimeReadoutReceiptV08(
            protocol=raw_chain.RUNTIME_RECEIPT_PROTOCOL_ID,
            **_identity_fields(runtime_role, self.signers),
            issued_at_utc=self.now - timedelta(minutes=6),
            expires_at_utc=self.expiry,
            nonce=_uuid(f"runtime:{arm}"),
            run_id=self.run_id,
            run_manifest_content_sha256=self.manifest.content_sha256,
            canonical_verification_content_sha256=self.canonical.content_sha256,
            canonical_task_receipt_content_sha256=source.canonical_task_receipt_content_sha256,
            task_index=index,
            arm=arm,
            episode_id=self.episode_id,
            implementation_bundle_sha256=source.implementation_bundle_sha256,
            raw_output_artifact_sha256=hashlib_sha(encoded),
            raw_output_content_sha256=output.content_sha256,
            process_started_at_utc=self.now - timedelta(minutes=8),
            process_finished_at_utc=self.now - timedelta(minutes=7),
            runtime_engine_sha256=self.runtime_engine_sha256,
        )
        runtime_receipt = raw_chain.sign_runtime_receipt_v0_8(
            unsigned_runtime,
            signer=self.signers[runtime_role],
        )
        broker_role = raw_chain.FormalRole.CAUSAL_BROKER
        event_start = self.now - timedelta(minutes=7, seconds=50)
        payloads = (
            step.readout_payload_sha256,
            step.action_payload_sha256,
            step.evaluator_truth_sha256,
            step.utility_payload_sha256,
        )
        unsigned_broker = raw_chain.CausalBrokerStepReceiptV08(
            protocol=raw_chain.BROKER_RECEIPT_PROTOCOL_ID,
            **_identity_fields(broker_role, self.signers),
            issued_at_utc=self.now - timedelta(minutes=5),
            expires_at_utc=self.expiry,
            nonce=_uuid(f"broker:{arm}:0"),
            run_id=self.run_id,
            run_manifest_content_sha256=self.manifest.content_sha256,
            runtime_receipt_content_sha256=runtime_receipt.content_sha256,
            task_index=index,
            arm=arm,
            episode_id=self.episode_id,
            step_index=0,
            decision_id=readout.decision_id,
            events=tuple(
                raw_chain.CausalBrokerEventV08(
                    sequence_index=event_index,
                    kind=kind,
                    observed_at_utc=event_start + timedelta(seconds=event_index),
                    payload_sha256=payload,
                )
                for event_index, (kind, payload) in enumerate(
                    zip(raw_chain.CAUSAL_EVENT_ORDER, payloads, strict=True)
                )
            ),
        )
        broker = raw_chain.sign_broker_receipt_v0_8(
            unsigned_broker,
            signer=self.signers[broker_role],
        )
        broker_hashes = (broker.content_sha256,)
        ingest_role = raw_chain.FormalRole.INGEST_CUSTODIAN
        unsigned_ingest = raw_chain.CustodyHopReceiptV08(
            protocol=raw_chain.CUSTODY_RECEIPT_PROTOCOL_ID,
            **_identity_fields(ingest_role, self.signers),
            issued_at_utc=self.now - timedelta(minutes=4),
            expires_at_utc=self.expiry,
            nonce=_uuid(f"custody:ingest:{arm}"),
            custody_role=raw_chain.CustodyRole.INGEST,
            run_id=self.run_id,
            run_manifest_content_sha256=self.manifest.content_sha256,
            task_index=index,
            arm=arm,
            episode_id=self.episode_id,
            raw_output_artifact_sha256=hashlib_sha(encoded),
            raw_output_content_sha256=output.content_sha256,
            runtime_receipt_content_sha256=runtime_receipt.content_sha256,
            broker_receipt_content_sha256=broker_hashes,
            parent_custody_receipt_sha256=None,
            storage_locator_sha256=content_sha256({"vault": "ingest", "arm": arm}),
        )
        ingest = raw_chain.sign_custody_hop_v0_8(
            unsigned_ingest,
            signer=self.signers[ingest_role],
        )
        archive_role = raw_chain.FormalRole.ARCHIVE_CUSTODIAN
        unsigned_archive = raw_chain.CustodyHopReceiptV08(
            protocol=raw_chain.CUSTODY_RECEIPT_PROTOCOL_ID,
            **_identity_fields(archive_role, self.signers),
            issued_at_utc=self.now - timedelta(minutes=3),
            expires_at_utc=self.expiry,
            nonce=_uuid(f"custody:archive:{arm}"),
            custody_role=raw_chain.CustodyRole.ARCHIVE,
            run_id=self.run_id,
            run_manifest_content_sha256=self.manifest.content_sha256,
            task_index=index,
            arm=arm,
            episode_id=self.episode_id,
            raw_output_artifact_sha256=hashlib_sha(encoded),
            raw_output_content_sha256=output.content_sha256,
            runtime_receipt_content_sha256=runtime_receipt.content_sha256,
            broker_receipt_content_sha256=broker_hashes,
            parent_custody_receipt_sha256=ingest.content_sha256,
            storage_locator_sha256=content_sha256({"vault": "archive", "arm": arm}),
        )
        archive = raw_chain.sign_custody_hop_v0_8(
            unsigned_archive,
            signer=self.signers[archive_role],
        )
        return raw_chain.RawTaskEvidenceV08(
            raw_output_artifact_sha256=hashlib_sha(encoded),
            raw_output_content_sha256=output.content_sha256,
            output=output,
            runtime_receipt=runtime_receipt,
            broker_receipts=(broker,),
            custody_hops=(ingest, archive),
        )


def hashlib_sha(encoded: bytes) -> str:
    import hashlib

    return hashlib.sha256(encoded).hexdigest()


def test_current_policy_registers_chain_but_remains_fail_closed() -> None:
    policy = raw_chain.load_raw_formal_chain_policy_v0_8()
    status = raw_chain.current_gate_b_v0_8_formal_status()
    assert policy.gate_b_protocol_content_sha256 == content_sha256(
        canonical_protocol_payload_v0_8()
    )
    assert status.blockers == (
        "independent_trust_anchors_not_enrolled",
        "verifier_owned_persistent_replay_registry_not_enrolled",
        "raw_formal_execution_not_registered",
    )
    assert status.raw_formal_execution_verified is False
    assert status.formal_gate_b_passed is False
    assert status.seven_operator_ablation_authorized is False
    assert HISTORICAL_V0_7_STATUS == "INVALIDATED_SUPERSEDED_FOR_FUTURE"


def test_complete_enrolled_candidate_chain_recomputes_positive_but_cannot_authorize(
    tmp_path: Path,
) -> None:
    fixture = _Fixture(tmp_path)
    verified = raw_chain.verify_raw_chain_candidate_v0_8(
        fixture.chain,
        policy=fixture.policy,
        trust_manifest=fixture.trust,
        replay_registry=fixture.registry,
        raw_artifact_paths=fixture.paths,
    )
    assert verified.typed_relations_passed is True
    assert verified.formal_gate_b_passed is False
    assert verified.seven_operator_ablation_authorized is False
    assert verified.consumed_nonce_count == 2 + len(EXPECTED_ARMS) * 4 + 1


def test_honest_chronology_has_no_backdating_or_future_hash_cycle(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    assert fixture.manifest.issued_at_utc < fixture.canonical.issued_at_utc
    assert fixture.canonical.parent_run_manifest_content_sha256 == (fixture.manifest.content_sha256)
    assert not hasattr(fixture.manifest, "canonical_verification_content_sha256")
    raw_chain.verify_raw_chain_candidate_v0_8(
        fixture.chain,
        policy=fixture.policy,
        trust_manifest=fixture.trust,
        replay_registry=fixture.registry,
        raw_artifact_paths=fixture.paths,
    )


def test_canonical_receipt_cannot_substitute_preregistration_parent(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    role = raw_chain.FormalRole.CANONICAL_EXECUTION_VERIFIER
    unsigned = fixture.canonical.model_copy(
        update={"parent_run_manifest_content_sha256": "e" * 64, "attestation": None}
    )
    substituted = raw_chain.sign_canonical_verification_v0_8(
        unsigned,
        signer=fixture.signers[role],
    )
    chain = fixture.chain.model_copy(update={"canonical_verification": substituted})
    with pytest.raises(ValueError, match="preregistration parent"):
        raw_chain.verify_raw_chain_candidate_v0_8(
            chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_replay_of_complete_signed_chain_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    kwargs = {
        "policy": fixture.policy,
        "trust_manifest": fixture.trust,
        "replay_registry": fixture.registry,
        "raw_artifact_paths": fixture.paths,
    }
    raw_chain.verify_raw_chain_candidate_v0_8(fixture.chain, **kwargs)
    with pytest.raises(ValueError, match="replay detected"):
        raw_chain.verify_raw_chain_candidate_v0_8(fixture.chain, **kwargs)


def test_fresh_registry_clone_at_another_path_is_not_the_enrolled_registry(
    tmp_path: Path,
) -> None:
    fixture = _Fixture(tmp_path)
    clone = raw_chain.PersistentReplayRegistryV08(
        path=tmp_path / "caller-clone.sqlite3",
        registry_id=fixture.registry_id,
        enrollment_sha256=fixture.registry_enrollment,
        initialize=True,
    )
    with pytest.raises(ValueError, match="differs from policy enrollment"):
        raw_chain.verify_raw_chain_candidate_v0_8(
            fixture.chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=clone,
            raw_artifact_paths=fixture.paths,
        )


def test_same_path_registry_replacement_is_rejected_before_replay_commit(
    tmp_path: Path,
) -> None:
    fixture = _Fixture(tmp_path)
    enrolled_path = fixture.registry.path
    original = tmp_path / "enrolled-original.sqlite3"
    enrolled_path.replace(original)
    shutil.copy2(original, enrolled_path)
    with pytest.raises(ValueError, match="stable storage identity changed"):
        raw_chain.verify_raw_chain_candidate_v0_8(
            fixture.chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_forged_complete_chain_cannot_use_unenrolled_current_policy(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    with pytest.raises(Exception, match="not enrolled"):
        raw_chain.verify_raw_chain_candidate_v0_8(
            fixture.chain,
            policy=raw_chain.load_raw_formal_chain_policy_v0_8(),
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_exact_arm_episode_coverage_rejects_missing_task(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    with pytest.raises(ValueError, match="exact arm-by-episode coverage"):
        fixture.chain.model_copy(update={"tasks": fixture.chain.tasks[:-1]}).model_validate(
            fixture.chain.model_copy(update={"tasks": fixture.chain.tasks[:-1]}).model_dump(
                mode="python"
            )
        )


def test_runtime_action_must_equal_canonical_source_trace(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    source = fixture.canonical.tasks[0]
    altered_step = source.steps[0].model_copy(
        update={"runtime_action_id": fixture.canonical.tasks[8].steps[0].runtime_action_id}
    )
    altered_source = source.model_copy(update={"steps": (altered_step,)})
    altered_canonical = fixture.canonical.model_copy(
        update={"tasks": (altered_source, *fixture.canonical.tasks[1:])}
    )
    altered_chain = fixture.chain.model_copy(update={"canonical_verification": altered_canonical})
    with pytest.raises((AttestationError, ValueError)):
        raw_chain.verify_raw_chain_candidate_v0_8(
            altered_chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_runtime_engine_must_match_preregistered_canonical_binding(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    first = fixture.chain.tasks[0]
    role = raw_chain.FormalRole.RUNTIME_READOUT_EXECUTOR
    unsigned = first.runtime_receipt.model_copy(
        update={
            "runtime_engine_sha256": content_sha256({"engine": "substituted"}),
            "attestation": None,
        }
    )
    substituted = raw_chain.sign_runtime_receipt_v0_8(
        unsigned,
        signer=fixture.signers[role],
    )
    altered_task = first.model_copy(update={"runtime_receipt": substituted})
    altered_chain = fixture.chain.model_copy(
        update={"tasks": (altered_task, *fixture.chain.tasks[1:])}
    )
    with pytest.raises(ValueError, match="runtime receipt changed its raw artifact/source"):
        raw_chain.verify_raw_chain_candidate_v0_8(
            altered_chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_raw_trace_digests_must_be_derived_from_live_readout(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    step = fixture.chain.tasks[0].output.steps[0]
    for field, message in (
        ("belief_trace_sha256", "belief trace digest"),
        ("action_policy_trace_sha256", "action trace digest"),
    ):
        altered = step.model_copy(update={field: "f" * 64})
        with pytest.raises(ValueError, match=message):
            raw_chain.RawRuntimeStepV08.model_validate(altered.model_dump(mode="python"))


def test_causal_broker_payload_substitution_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    first = fixture.chain.tasks[0]
    broker = first.broker_receipts[0]
    altered_event = broker.events[0].model_copy(update={"payload_sha256": "f" * 64})
    altered_broker = broker.model_copy(update={"events": (altered_event, *broker.events[1:])})
    altered_task = first.model_copy(update={"broker_receipts": (altered_broker,)})
    altered_chain = fixture.chain.model_copy(
        update={"tasks": (altered_task, *fixture.chain.tasks[1:])}
    )
    with pytest.raises((AttestationError, ValueError)):
        raw_chain.verify_raw_chain_candidate_v0_8(
            altered_chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_non_evaluation_step_still_requires_exact_dense_public_support(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    step = fixture.chain.tasks[0].output.steps[0]
    malformed_belief = EpisodeDistribution(
        kind=DistributionKind.BELIEF,
        schema_id=BELIEF_SCHEMA_ID,
        ontology_manifest_sha256=fixture.ontology.manifest_sha256,
        support=("attacker-only-hidden-state",),
        probabilities=(1.0,),
    )
    non_evaluation_step = step.model_copy(
        update={
            "step_index": 1,
            "readout": replace(step.readout, belief=malformed_belief),
        }
    )
    with pytest.raises(ValueError, match="exact public support"):
        raw_chain._validate_runtime_step_against_public_contract(
            non_evaluation_step,
            ontology=fixture.ontology,
            projection=fixture.projections[EXPECTED_ARMS[0]],
        )


def test_causal_broker_rejects_truth_before_action(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    broker = fixture.chain.tasks[0].broker_receipts[0]
    reordered = (
        broker.events[0],
        broker.events[2],
        broker.events[1],
        broker.events[3],
    )
    with pytest.raises(ValueError, match="event order"):
        broker.model_copy(update={"events": reordered}).model_validate(
            broker.model_copy(update={"events": reordered}).model_dump(mode="python")
        )


def test_custody_parent_rewrite_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    first = fixture.chain.tasks[0]
    archive = first.custody_hops[1].model_copy(update={"parent_custody_receipt_sha256": "a" * 64})
    with pytest.raises(ValueError, match="ingest parent"):
        first.model_copy(update={"custody_hops": (first.custody_hops[0], archive)}).model_validate(
            first.model_copy(update={"custody_hops": (first.custody_hops[0], archive)}).model_dump(
                mode="python"
            )
        )


def test_same_key_for_two_formal_roles_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    anchors = list(fixture.trust.anchors)
    first = anchors[0]
    anchors[1] = anchors[1].model_copy(
        update={
            "key_id": first.key_id,
            "public_key_base64": first.public_key_base64,
            "public_key_sha256": first.public_key_sha256,
        }
    )
    with pytest.raises(ValueError, match="independent key id"):
        fixture.trust.model_copy(update={"anchors": tuple(anchors)}).model_validate(
            fixture.trust.model_copy(update={"anchors": tuple(anchors)}).model_dump(mode="python")
        )


def test_stale_signed_runtime_receipt_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    first = fixture.chain.tasks[0]
    stale = first.runtime_receipt.model_copy(
        update={
            "issued_at_utc": fixture.now - timedelta(days=2),
            "expires_at_utc": fixture.now - timedelta(days=1, hours=1),
        }
    )
    altered = first.model_copy(update={"runtime_receipt": stale})
    chain = fixture.chain.model_copy(update={"tasks": (altered, *fixture.chain.tasks[1:])})
    with pytest.raises((AttestationError, ValueError)):
        raw_chain.verify_raw_chain_candidate_v0_8(
            chain,
            policy=fixture.policy,
            trust_manifest=fixture.trust,
            replay_registry=fixture.registry,
            raw_artifact_paths=fixture.paths,
        )


def test_backdated_signed_record_before_anchor_enrollment_is_rejected(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    role = raw_chain.FormalRole.CANONICAL_EXECUTION_VERIFIER
    unsigned = fixture.canonical.model_copy(
        update={
            "issued_at_utc": fixture.t0 - timedelta(minutes=2),
            "expires_at_utc": fixture.now + timedelta(minutes=1),
            "attestation": None,
        }
    )
    backdated = raw_chain.sign_canonical_verification_v0_8(
        unsigned,
        signer=fixture.signers[role],
    )
    with pytest.raises(ValueError, match="stale or not yet valid"):
        raw_chain._verify_signed_record(
            backdated,
            manifest=fixture.trust,
            expected_role=role,
            domain=raw_chain.CANONICAL_VERIFICATION_DOMAIN,
            now_utc=fixture.now,
        )


def test_raw_artifact_loader_rejects_noncanonical_and_duplicate_json(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    source_path = fixture.paths[(EXPECTED_ARMS[0], fixture.episode_id)]
    payload = source_path.read_text(encoding="utf-8")
    noncanonical = tmp_path / "pretty.json"
    noncanonical.write_text("  " + payload, encoding="utf-8")
    with pytest.raises(ValueError, match="not canonical JSON"):
        raw_chain.load_raw_runtime_artifact_v0_8(noncanonical)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(payload.replace("{", '{"protocol":"shadow",', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        raw_chain.load_raw_runtime_artifact_v0_8(duplicate)


def test_raw_artifact_loader_rejects_hidden_nested_runtime_fields(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    source_path = fixture.paths[(EXPECTED_ARMS[0], fixture.episode_id)]
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["steps"][0]["readout"]["selected_runtime_action"]["hidden_opcode"] = "erase"
    hidden = tmp_path / "hidden-runtime-field.json"
    hidden.write_text(canonical_json(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=r"Unexpected keyword argument|hidden or unregistered"):
        raw_chain.load_raw_runtime_artifact_v0_8(hidden)


def test_raw_artifact_loader_rejects_symlink(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    source = fixture.paths[(EXPECTED_ARMS[0], fixture.episode_id)]
    link = tmp_path / "raw-link.json"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="without following links"):
        raw_chain.load_raw_runtime_artifact_v0_8(link)


def test_raw_artifact_loader_detects_same_fd_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _Fixture(tmp_path)
    source = fixture.paths[(EXPECTED_ARMS[0], fixture.episode_id)]
    real_fstat = raw_chain.os.fstat
    call_count = 0

    def shifted_fstat(descriptor: int) -> object:
        nonlocal call_count
        call_count += 1
        value = real_fstat(descriptor)
        if call_count == 1:
            return value
        return SimpleNamespace(
            st_dev=value.st_dev,
            st_ino=value.st_ino,
            st_size=value.st_size,
            st_mtime_ns=value.st_mtime_ns + 1,
            st_ctime_ns=value.st_ctime_ns,
            st_mode=value.st_mode,
            st_nlink=value.st_nlink,
        )

    monkeypatch.setattr(raw_chain.os, "fstat", shifted_fstat)
    with pytest.raises(ValueError, match="changed while being read"):
        raw_chain.load_raw_runtime_artifact_v0_8(source)
