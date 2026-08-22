"""Regression tests for the project-one six-route adversarial review.

See ``docs/reviews/项目一六路线_对抗复审报告_2026-08-21.md``.  These pin the
three medium-severity findings so a later fix (or regression) is visible:

* F1 — habit-model residual mode returns ``pseudo_counts`` that do not
  reconstruct the returned ``probabilities`` (xfail-strict: flips when fixed).
* F2 — resident isolation only gates the shared household channel; a known
  non-resident still builds its own person model.  Two characterization guards.
* F6 — fair-ablation matched budgets are validated on *declaration* only, with
  no measured-usage field to bind them to.

The high-severity finding (F3, CF-BOCPD) is a specification-vs-implementation
mismatch, not a failing assertion, so it lives in the review doc, not here.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from test_observation_aware_habits import habit_evidence

from cpswm.system.evaluation_operations.fair_ablation import (
    FairAblationArm,
    FairAblationManifest,
    ModelBudget,
    ObservationBudget,
    TuningBudget,
)
from cpswm.world_model.habits_transitions import HierarchicalDirichletHabitModel

L1 = UUID(int=9001)
L2 = UUID(int=9002)
OBJ = UUID(int=9100)
CTX = "weekday|breakfast"


def _feed(model, metadata_factory, now, *, location, actor, times=1):
    for _ in range(times):
        model.update(
            habit_evidence(
                metadata_factory,
                now,
                object_id=OBJ,
                location_id=location,
                actor_posterior={str(actor): 1.0},
                context_key=CTX,
            )
        )


# --- F1: residual-mode audit reconstruction (fixed 2026-08-22) ----------------


def test_residual_pseudo_counts_reconstruct_probabilities(metadata_factory, now):
    model = HierarchicalDirichletHabitModel(locations=[L1, L2], actor_residual_weight=0.5)
    actor = uuid4()
    _feed(model, metadata_factory, now, location=L1, actor=actor, times=3)
    _feed(model, metadata_factory, now, location=L2, actor=actor, times=1)

    prediction = model.predict(
        household_id=metadata_factory().household_id,
        person_id=actor,
        object_instance_id=OBJ,
        context_key=CTX,
    )
    total = sum(prediction.pseudo_counts.values())
    reconstructed = {loc: count / total for loc, count in prediction.pseudo_counts.items()}
    for location, probability in prediction.probabilities.items():
        assert reconstructed[location] == pytest.approx(probability, abs=1e-9)


# --- F2: resident isolation scope --------------------------------------------


def test_visitor_placement_does_not_move_owner_prediction(metadata_factory, now):
    """The protective half of isolation: a visitor must not move the owner."""

    household_id = metadata_factory().household_id
    owner = uuid4()
    visitor = uuid4()
    model = HierarchicalDirichletHabitModel(locations=[L1, L2], resident_actor_keys=[owner])

    _feed(model, metadata_factory, now, location=L1, actor=owner, times=4)
    before = model.predict(
        household_id=household_id, person_id=owner, object_instance_id=OBJ, context_key=CTX
    )
    _feed(model, metadata_factory, now, location=L2, actor=visitor, times=4)
    after = model.predict(
        household_id=household_id, person_id=owner, object_instance_id=OBJ, context_key=CTX
    )

    assert after.probabilities == before.probabilities
    # The visitor mass is quarantined into the non-resident store, not dropped.
    assert (
        model.isolated_nonresident_count(
            household_id=household_id, object_instance_id=OBJ, location_id=L2
        )
        > 0.0
    )


def test_isolation_does_not_quarantine_a_known_visitors_own_model(metadata_factory, now):
    """The scope limit F2 documents: isolation gates only the shared channel.

    A known (non-``unknown_actor``) visitor still accumulates its own person
    model, so 'non-resident quarantine' is narrower than the name implies.
    """

    household_id = metadata_factory().household_id
    owner = uuid4()
    visitor = uuid4()
    model = HierarchicalDirichletHabitModel(locations=[L1, L2], resident_actor_keys=[owner])

    _feed(model, metadata_factory, now, location=L2, actor=visitor, times=4)
    visitor_prediction = model.predict(
        household_id=household_id, person_id=visitor, object_instance_id=OBJ, context_key=CTX
    )
    # The visitor's own person channel learned L2 despite being non-resident.
    assert visitor_prediction.probabilities[L2] > visitor_prediction.probabilities[L1]


# --- F6: matched budgets are declaration-only --------------------------------


_HEX = "a" * 64


def _arm(arm_id: str, tuning_run_id: UUID, *, parameter_count: int) -> FairAblationArm:
    return FairAblationArm(
        arm_id=arm_id,
        model_version="model@1",
        components=("component",),
        observation_budget=ObservationBudget(
            maximum_observation_actions=5,
            maximum_user_interruptions=1,
            maximum_observation_cost=1.0,
            maximum_elapsed_time_seconds=60.0,
        ),
        model_budget=ModelBudget(
            maximum_train_compute_units=1.0,
            maximum_inference_compute_units=1.0,
            maximum_persistent_memory_bytes=1024,
            maximum_latency_ms=10.0,
            maximum_parameter_count=parameter_count,
        ),
        tuning_budget=TuningBudget(
            maximum_trials=1,
            maximum_compute_units=1.0,
            validation_split_sha256=_HEX,
            objective_name="utility",
        ),
        independent_tuning_run_id=tuning_run_id,
        observation_trace_sha256=_HEX,
        test_split_sha256=_HEX,
    )


def test_matched_budget_is_declared_not_measured():
    # An absurdly small declared budget (1 parameter) validates fine, because
    # the manifest compares declared budgets and never binds a measured usage.
    manifest = FairAblationManifest(
        experiment_id=uuid4(),
        baseline_arm_id="baseline",
        arms=(
            _arm("baseline", uuid4(), parameter_count=1),
            _arm("candidate", uuid4(), parameter_count=1),
        ),
    )
    assert manifest.arms[0].model_budget.maximum_parameter_count == 1
    # There is no field anywhere to record what an arm actually consumed, so the
    # matched-budget guarantee is a declaration, not a measurement (cf. F0 F-4).
    for field_name in FairAblationArm.model_fields:
        assert "measured" not in field_name
        assert "actual" not in field_name
