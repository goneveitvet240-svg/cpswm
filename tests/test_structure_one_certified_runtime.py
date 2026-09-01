from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cpswm.contracts import BaseRecordMetadata, ContractModel, SourceType
from cpswm.system.m21_query_compiler import (
    DeterministicM21QueryCompiler,
    QueryLexiconEntry,
)
from cpswm.system.structure_one_ingress import (
    ActorInputAuthority,
    EvidenceAuthority,
    FactEligibility,
    IngressStatus,
    StructureOneCertifiedIngress,
    StructureOneContentKind,
    StructureOneIngressError,
    StructureOneModule,
    StructureOneWriteRequest,
)
from cpswm.system.structure_one_runtime import StructureOneRuntime


class _TrainingPayload(ContractModel):
    metadata: BaseRecordMetadata
    location: str


def _training_payload(source_type: SourceType) -> _TrainingPayload:
    record_id = uuid4()
    return _TrainingPayload(
        metadata=BaseRecordMetadata(
            record_id=record_id,
            schema_name="cpswm.StructureOneTrainingAttackFixture",
            schema_version="0.1.0",
            household_id=uuid4(),
            session_id=uuid4(),
            recorded_time=datetime.now(UTC),
            source_type=source_type,
            source_id="structure-one-training-attack",
            trace_id=uuid4(),
        ),
        location="drawer",
    )


def test_certified_runtime_rejects_hard_actor_truth() -> None:
    ingress = StructureOneCertifiedIngress()
    with pytest.raises(StructureOneIngressError, match="hard actor truth"):
        ingress.submit(
            StructureOneWriteRequest(
                target_module=StructureOneModule.BELIEF_STATE,
                content_kind=StructureOneContentKind.DIRECT_OBSERVATION,
                authority=EvidenceAuthority.SENSOR,
                fact_eligibility=FactEligibility.EVIDENCE,
                source_record_ids=(uuid4(),),
                actor_input_authority=ActorInputAuthority.HARD_TRUTH,
            ),
            {"location": "drawer"},
        )


def test_prediction_cannot_train_habit_ledger() -> None:
    ingress = StructureOneCertifiedIngress()
    with pytest.raises(StructureOneIngressError):
        ingress.submit(
            StructureOneWriteRequest(
                target_module=StructureOneModule.HABIT_LEDGER,
                content_kind=StructureOneContentKind.FUTURE_PREDICTION,
                authority=EvidenceAuthority.MODEL_PREDICTION,
                fact_eligibility=FactEligibility.PREDICTION_ONLY,
                source_record_ids=(uuid4(),),
                training_eligible=True,
            ),
            {"predicted_location": "drawer"},
        )


def test_model_payload_cannot_self_declare_sensor_authority_to_train_habits() -> None:
    ingress = StructureOneCertifiedIngress()
    payload = _training_payload(SourceType.MODEL)
    request = StructureOneWriteRequest(
        target_module=StructureOneModule.HABIT_LEDGER,
        content_kind=StructureOneContentKind.HABIT_EVIDENCE,
        authority=EvidenceAuthority.SENSOR,
        fact_eligibility=FactEligibility.EVIDENCE,
        source_record_ids=(payload.metadata.record_id,),
        training_eligible=True,
    )

    with pytest.raises(StructureOneIngressError, match="payload provenance"):
        ingress.submit(request, payload)


def test_sensor_payload_can_reach_habit_training_with_bound_record_id() -> None:
    accepted = []
    ingress = StructureOneCertifiedIngress(
        backends={StructureOneModule.HABIT_LEDGER: accepted.append}
    )
    payload = _training_payload(SourceType.SENSOR)
    receipt = ingress.submit(
        StructureOneWriteRequest(
            target_module=StructureOneModule.HABIT_LEDGER,
            content_kind=StructureOneContentKind.HABIT_EVIDENCE,
            authority=EvidenceAuthority.SENSOR,
            fact_eligibility=FactEligibility.EVIDENCE,
            source_record_ids=(payload.metadata.record_id,),
            training_eligible=True,
        ),
        payload,
    )

    assert receipt.status is IngressStatus.APPLIED
    assert accepted[0].payload == payload


def test_ingress_rejects_payload_mapping_key_collision() -> None:
    ingress = StructureOneCertifiedIngress()
    request = StructureOneWriteRequest(
        target_module=StructureOneModule.PROVENANCE,
        content_kind=StructureOneContentKind.DIRECT_OBSERVATION,
        authority=EvidenceAuthority.SENSOR,
        fact_eligibility=FactEligibility.EVIDENCE,
        source_record_ids=(uuid4(),),
    )

    with pytest.raises(StructureOneIngressError, match="mapping keys collide"):
        ingress.submit(request, {1: "attacker", "1": "trusted"})


def test_registered_backend_is_reachable_only_after_certification() -> None:
    accepted = []
    ingress = StructureOneCertifiedIngress(
        backends={StructureOneModule.HIDDEN_EVENT_LEDGER: accepted.append}
    )
    receipt = ingress.submit(
        StructureOneWriteRequest(
            target_module=StructureOneModule.HIDDEN_EVENT_LEDGER,
            content_kind=StructureOneContentKind.INFERRED_EVENT,
            authority=EvidenceAuthority.ROBOT_INFERENCE,
            fact_eligibility=FactEligibility.HYPOTHESIS_ONLY,
            source_record_ids=(uuid4(),),
            actor_input_authority=ActorInputAuthority.ROBOT_POSTERIOR,
        ),
        {"candidate": "unobserved_move"},
    )
    assert receipt.status is IngressStatus.APPLIED
    assert accepted[0].request.fact_eligibility is FactEligibility.HYPOTHESIS_ONLY


def test_m21_baseline_abstains_instead_of_inventing_unknown_entity() -> None:
    compiler = DeterministicM21QueryCompiler(lexicon=(QueryLexiconEntry("keys", ("keys", "钥匙")),))
    query = compiler.compile("我的护照在哪里")
    assert query.abstain is True
    assert query.category_candidates == ()


def test_runtime_surfaces_method_choices_instead_of_selecting_them() -> None:
    compiler = DeterministicM21QueryCompiler(lexicon=(QueryLexiconEntry("keys", ("keys", "钥匙")),))
    runtime = StructureOneRuntime(ingress=StructureOneCertifiedIngress(), query_compiler=compiler)
    readiness = runtime.readiness()
    assert "cross_day_object_identity_method" in readiness.unresolved_design_choices
    assert "commonsense_and_object_property_source" in readiness.unresolved_design_choices
    assert "hidden_event_inference_method" in readiness.unresolved_design_choices
    assert "formal_habit_backend_replacement" in readiness.unresolved_design_choices
    assert readiness.fully_operational is False
