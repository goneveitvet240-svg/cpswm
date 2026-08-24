"""Adversarial self-check for the joint CF-BOCPD fixes (review 2026-08-21).

Attacks the unified post-pruning accounting (fix 1), the segment/noise split
(fix 2), and the real gated write path (fix 3/4) on their hardest cases.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cpswm.contracts import (
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationOpportunityRecord,
    SourceType,
)
from cpswm.world_model.habits_transitions import (
    CauseGatedHabitConsolidation,
    CauseSignalFrame,
    ChangeCause,
    GatedHierarchicalDirichletConsolidator,
    HierarchicalDirichletHabitModel,
    JointCauseFactorizedBOCPD,
    ObservationPropensityCorrector,
)

BASE = datetime(2026, 8, 1, tzinfo=UTC)


def test_accounting_partitions_probability_on_adversarial_random_streams():
    rng = random.Random(20260821)
    for _ in range(50):
        frames = tuple(
            CauseSignalFrame(
                timestamp=BASE + timedelta(days=index),
                signals={cause: rng.random() for cause in ChangeCause},
            )
            for index in range(12)
        )
        result = JointCauseFactorizedBOCPD(beam_width=rng.choice([4, 8, 16])).run(
            frames, warmup_steps=1
        )
        for snapshot in result.snapshots:
            partition = (
                snapshot.continue_probability
                + snapshot.segment_change_probability
                + snapshot.transient_noise_probability
            )
            assert abs(partition - 1.0) < 1e-9
            assert abs(sum(snapshot.joint_run_length_cause_posterior.values()) - 1.0) < 1e-9


def test_persistent_noise_never_opens_the_habit_block():
    # A relentless high-ambiguity stream: noise mass is large every step, but it
    # is not a segment change and must never write habit parameters.
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.5 + 0.4 * ((index % 2) - 0.5),  # jitter, no regime
                ChangeCause.NOISE: 0.85,
            },
        )
        for index in range(12)
    )
    result = JointCauseFactorizedBOCPD().run(frames, warmup_steps=2)
    gate = CauseGatedHabitConsolidation(change_threshold=0.3)
    for snapshot in result.snapshots:
        assert not gate.decide(snapshot).habit_block_writable
        assert gate.habit_consolidation_weight(snapshot) == 0.0


def test_simultaneous_shift_opens_exact_union_of_attributed_blocks(metadata_factory):
    # Observation and habit shift on the same day: the multi-label state makes
    # the joint explanation explicit instead of forcing an ambiguous singleton.
    frames = tuple(
        CauseSignalFrame(
            timestamp=BASE + timedelta(days=index),
            signals={
                ChangeCause.OBSERVATION: 0.2 if index < 3 else 0.9,
                ChangeCause.ACTOR: 0.2,
                ChangeCause.HABIT: 0.2 if index < 3 else 0.9,
                ChangeCause.NOISE: 0.1,
            },
        )
        for index in range(6)
    )
    result = JointCauseFactorizedBOCPD().run(frames, warmup_steps=2)
    gate = CauseGatedHabitConsolidation(change_threshold=0.3, attribution_margin=0.3)
    shift = result.snapshots[3]
    decision = gate.decide(shift)
    assert not decision.ambiguous
    assert decision.attributed_cause is None
    assert decision.attributed_causes == frozenset({ChangeCause.OBSERVATION, ChangeCause.HABIT})
    assert decision.writable_blocks == decision.attributed_causes
    assert decision.habit_block_writable


def _bound_pair(metadata_factory, person):
    opportunity = ObservationOpportunityRecord(
        metadata=metadata_factory(
            schema_name="cpswm.ObservationOpportunityRecord", source_type=SourceType.SIMULATION
        ),
        observation_action_id=uuid4(),
        opportunity_time=BASE,
        selected=True,
        selection_probability=1.0,
        p_visible_given_state=1.0,
        p_detect_given_visible=1.0,
        likelihood_model_id="fixture@0.1",
    )
    evidence = HabitLearningEvidence(
        metadata=opportunity.metadata.model_copy(
            update={"record_id": uuid4(), "schema_name": "cpswm.HabitLearningEvidence"}
        ),
        object_instance_id=UUID(int=5),
        location_id=UUID(int=1),
        event_time=BASE,
        context_key="weekday|breakfast",
        actor_posterior={str(person): 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        source_record_ids=(uuid4(),),
        observation_opportunity_id=opportunity.metadata.record_id,
    )
    return opportunity, evidence


def test_no_snapshot_can_force_a_rejected_write_to_change_the_real_model(metadata_factory):
    model = HierarchicalDirichletHabitModel(locations=[UUID(int=1), UUID(int=2)])
    consolidator = GatedHierarchicalDirichletConsolidator(
        model,
        gate=CauseGatedHabitConsolidation(change_threshold=0.3),
        propensity_corrector=ObservationPropensityCorrector(),
    )
    opportunity, evidence = _bound_pair(metadata_factory, uuid4())
    rng = random.Random(7)
    for _ in range(40):
        frames = tuple(
            CauseSignalFrame(
                timestamp=BASE + timedelta(days=index),
                signals={cause: rng.random() for cause in ChangeCause},
            )
            for index in range(8)
        )
        for snapshot in JointCauseFactorizedBOCPD().run(frames, warmup_steps=1).snapshots:
            audit = consolidator.propose_consolidation(snapshot, evidence, opportunity)
            # Every rejected write is a proven no-op on the real model.
            if not audit.accepted:
                assert audit.before_hash == audit.after_hash
    assert consolidator.canonical_log.verify_chain()
    # De-duplication means the one evidence record writes at most once overall.
    assert sum(entry.payload.get("accepted") for entry in consolidator.canonical_log.entries()) <= 1
