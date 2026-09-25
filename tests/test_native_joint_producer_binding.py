"""Actual implementation identity supplements the configured artifact declaration."""

from types import MethodType

import pytest
from test_native_joint_production import JointFixture

from cpswm.system.native_joint_production import producer_implementation_binding


class Replacement(JointFixture):
    def produce(self, context):
        return super().produce(context)


def test_declared_artifact_does_not_authorize_a_replacement_implementation():
    original, replacement = JointFixture(), Replacement()
    assert original.binding_sha256 == replacement.binding_sha256
    assert producer_implementation_binding(original) != producer_implementation_binding(replacement)


def test_recovery_identity_is_stable_across_instances_and_mutable_inference_state():
    original, recovered = JointFixture(), JointFixture()
    recovered.calls = 77
    assert producer_implementation_binding(original) == producer_implementation_binding(recovered)
    assert producer_implementation_binding(None) is None


def test_instance_callable_override_cannot_keep_the_same_implementation_binding():
    producer = JointFixture()
    producer.produce = MethodType(JointFixture.produce, producer)
    with pytest.raises(ValueError, match="declared instance methods"):
        producer_implementation_binding(producer)


def test_loaded_code_change_is_detected_even_if_source_file_and_class_symbol_match(monkeypatch):
    producer = JointFixture()
    original = producer_implementation_binding(producer)

    def replacement(self, context):
        return None

    monkeypatch.setattr(JointFixture.produce, "__code__", replacement.__code__)
    assert producer_implementation_binding(producer) != original


def test_recovery_verifies_actual_restored_model_state(tmp_path):
    from test_continuous_state_recovery import DurableFixtureProducer
    from test_native_joint_full_replay import fixture_method_profile
    from test_native_joint_production import setup

    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

    _, store, _, builder, _ = setup(tmp_path / "state.db", JointFixture())
    recovered = JointFixture()

    def corrupt(frame):
        if (
            frame.f_code is JointFixture.restore_state.__code__
            and frame.f_locals["self"] is recovered
        ):
            recovered.calls = -99

    try:
        with (
            fixture_method_profile(corrupt),
            pytest.raises(ValueError, match="restored state differs"),
        ):
            ContinuousEvidenceInput.resume(
                store,
                producer=DurableFixtureProducer(),
                context_builder=builder,
                joint_producer=recovered,
            )
    finally:
        store.close()
