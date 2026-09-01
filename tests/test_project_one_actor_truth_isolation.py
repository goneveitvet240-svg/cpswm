"""RQ8 死亡测试: 硬 actor truth 不得成为普通模型输入.

The audit line this file implements is:

    RQ8 多人归因 -- 核心路线正确 -- 接入前缺口: 禁止把硬 actor truth 作为普通模型输入.

Each test states what it would take for the test to fail, because a guard whose
failure mode is unclear gets deleted the first time it is inconvenient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cpswm.system.evaluation_operations.project_one_actor_evidence import (
    MASKED_ACTOR,
    UNKNOWN_ACTOR,
    ActorEvidencePolicy,
    ProjectOneActorChannel,
    ProjectOneActorEvidence,
    ProjectOneActorEvidenceProjector,
    audit_actor_truth_isolation,
    permute_actor_labels,
)
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_methods import (
    CategoricalBOCPDMethod,
    ContextFrequencyMethod,
    CoreHabitChainMethod,
    PersistenceMethod,
    build_first_batch,
)
from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneProtocolConfig

OWNER = "owner"
GUEST = "guest"
LOCATIONS = ("desk", "sofa", "kitchen")
START = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)


def _stream(count: int = 24) -> tuple[ProjectOneDatasetRecord, ...]:
    """A stream in which the guest is the reason the object moves.

    Owner days keep the object at ``desk``; guest days push it to ``sofa``.
    This is the exact configuration RQ8 is about -- if an arm knows who acted,
    the guest days are trivially explained away; if it does not, they look like
    a habit change.
    """

    records = []
    for index in range(count):
        guest_day = index % 4 == 3
        actor = GUEST if guest_day else OWNER
        location = "sofa" if guest_day else "desk"
        records.append(
            ProjectOneDatasetRecord(
                stream_id="rq8-stream",
                event_id=f"e{index:03d}",
                subject_id=OWNER,
                household_id="h1",
                object_id="cup",
                actor_id=actor,
                timestamp=START + timedelta(days=index),
                context_key="morning",
                context_value=float(index % 7),
                observed_location=location,
                observation_quality=0.9,
            )
        )
    return tuple(records)


def _chain(
    channel: ProjectOneActorChannel | None,
    *,
    allow_legacy_hard_actor: bool = False,
) -> CoreHabitChainMethod:
    return CoreHabitChainMethod(
        name="full",
        locations=LOCATIONS,
        owner_id=OWNER,
        household_id="h1",
        object_id="cup",
        config=ProjectOneProtocolConfig(),
        actor_channel=channel,
        allow_legacy_hard_actor=(
            allow_legacy_hard_actor
            or (channel is not None and channel.policy is ActorEvidencePolicy.LEGACY_HARD_ACTOR)
        ),
    )


def _channel(policy: ActorEvidencePolicy) -> ProjectOneActorChannel:
    projector = ProjectOneActorEvidenceProjector(policy=policy, owner_id=OWNER)
    return projector.project_stream(_stream(), support=(OWNER, GUEST, UNKNOWN_ACTOR))


def test_chain_default_is_actor_truth_isolated() -> None:
    chain = _chain(None)
    assert chain.actor_evidence_policy is ActorEvidencePolicy.ABSENT
    assert chain.actor_channel is not None
    assert chain.actor_channel.masks_actor_identity is True


def test_projector_does_not_infer_actor_support_from_future_stream() -> None:
    projector = ProjectOneActorEvidenceProjector(
        policy=ActorEvidencePolicy.CONTROLLED_NOISE,
        owner_id=OWNER,
    )
    channel = projector.project_stream(_stream())
    assert channel.support == (OWNER, UNKNOWN_ACTOR)


# ---------------------------------------------------------------------------
# The finding: the legacy wiring is not isolated
# ---------------------------------------------------------------------------


def test_the_frozen_legacy_wiring_reads_hard_actor_truth() -> None:
    """The v0.3 boundary fails isolation -- this is the RQ8 gap, made numeric.

    Fails if the legacy arm ever stops depending on ``actor_id``, which would
    mean the historical numbers no longer reproduce.
    """

    report = audit_actor_truth_isolation(
        lambda: _chain(None, allow_legacy_hard_actor=True),
        _stream(),
        policy=ActorEvidencePolicy.LEGACY_HARD_ACTOR,
        owner_id=OWNER,
    )
    assert not report.isolated
    assert report.diverged_events > 0
    assert report.first_divergence_event_id is not None


@pytest.mark.parametrize(
    "policy",
    [
        ActorEvidencePolicy.ABSENT,
        ActorEvidencePolicy.CONTROLLED_NOISE,
        ActorEvidencePolicy.ORACLE,
    ],
)
def test_every_channel_policy_isolates_the_arm_from_actor_truth(
    policy: ActorEvidencePolicy,
) -> None:
    """Permuting the hidden labels must not move a single prediction.

    Fails if any code path lets ``actor_id`` reach a subclass -- including the
    oracle path, which gets its certainty from the *channel*, never from the
    record.
    """

    channel = _channel(policy)
    report = audit_actor_truth_isolation(
        lambda: _chain(channel),
        _stream(),
        policy=policy,
        owner_id=OWNER,
    )
    assert report.isolated, report.summary()
    assert report.max_probability_gap == 0.0
    assert report.decision_flips == 0


def test_masking_is_structural_not_advisory() -> None:
    """The subclass literally receives ``masked_actor``.

    Fails if masking is ever moved from :meth:`observe` into each arm, where a
    new arm could forget it.
    """

    seen: list[str] = []
    channel = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    arm = _chain(channel)
    original_step = arm._step

    def spy(event, prior):  # type: ignore[no-untyped-def]
        seen.append(event.actor_id)
        return original_step(event, prior)

    arm._step = spy  # type: ignore[method-assign]
    arm.reset()
    arm._step = spy  # type: ignore[method-assign]
    for record in _stream():
        arm.observe(record)
    assert seen
    assert set(seen) == {MASKED_ACTOR}


def test_legacy_channel_object_still_exposes_the_true_actor() -> None:
    """``LEGACY_HARD_ACTOR`` must not silently start masking.

    Fails if someone "fixes" the legacy policy, which would break every frozen
    reproduction command in ``docs/experiments/``.
    """

    channel = ProjectOneActorChannel(
        policy=ActorEvidencePolicy.LEGACY_HARD_ACTOR,
        owner_id=OWNER,
        support=(OWNER, GUEST, UNKNOWN_ACTOR),
    )
    assert not channel.masks_actor_identity
    seen: list[str] = []
    arm = _chain(channel)
    original_step = arm._step

    def spy(event, prior):  # type: ignore[no-untyped-def]
        seen.append(event.actor_id)
        return original_step(event, prior)

    arm._step = spy  # type: ignore[method-assign]
    for record in _stream():
        arm.observe(record)
    assert {OWNER, GUEST} <= set(seen)


# ---------------------------------------------------------------------------
# The channel contract
# ---------------------------------------------------------------------------


def test_controlled_noise_keeps_uncertainty_and_oracle_does_not() -> None:
    """A controlled-noise channel that reached certainty would be an oracle."""

    noisy = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    oracle = _channel(ActorEvidencePolicy.ORACLE)
    for record in _stream():
        noisy_evidence = noisy.evidence_for(record.event_id)
        oracle_evidence = oracle.evidence_for(record.event_id)
        assert noisy_evidence is not None
        assert oracle_evidence is not None
        assert not noisy_evidence.is_certain
        assert oracle_evidence.is_certain
        assert oracle_evidence.owner_mass(OWNER) == float(record.actor_id == OWNER)


def test_controlled_noise_is_not_an_invertible_relabelling() -> None:
    """A constant confusion would be an oracle wearing a hat.

    Fails if the per-event jitter is removed, which would make the owner mass
    take exactly two values and be trivially decoded back to the true label.
    """

    channel = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    owner_masses = {
        round(channel.owner_mass(record.event_id), 12)
        for record in _stream()
        if record.actor_id == OWNER
    }
    assert len(owner_masses) > 1


def test_the_channel_is_deterministic_across_construction() -> None:
    """Two builds of the same stream must agree byte-for-byte."""

    first = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    second = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    assert first.config_payload() == second.config_payload()


def test_absent_policy_falls_back_to_a_declared_prior_not_to_a_guess() -> None:
    """With no person evidence the owner mass is the uniform share.

    Fails if a hand-picked constant is introduced, which would be a hidden
    tuning knob on exactly the quantity RQ8 studies.
    """

    channel = _channel(ActorEvidencePolicy.ABSENT)
    assert len(channel) == 0
    assert channel.owner_mass("e000") == pytest.approx(1.0 / 3.0)


def test_a_channel_cannot_smuggle_evidence_under_a_no_evidence_policy() -> None:
    evidence = ProjectOneActorEvidence(
        event_id="e000",
        actor_posterior={OWNER: 0.7, GUEST: 0.2, UNKNOWN_ACTOR: 0.1},
        reference_actor_prior={OWNER: 1 / 3, GUEST: 1 / 3, UNKNOWN_ACTOR: 1 / 3},
        evidence_track="controlled_noise",
        evidence_model_id="m",
    )
    for policy in (ActorEvidencePolicy.ABSENT, ActorEvidencePolicy.LEGACY_HARD_ACTOR):
        with pytest.raises(ValueError, match="cannot carry actor evidence"):
            ProjectOneActorChannel(policy=policy, owner_id=OWNER, evidence=(evidence,))


def test_actor_evidence_rejects_a_posterior_that_is_not_a_distribution() -> None:
    with pytest.raises(ValueError, match="must sum to 1"):
        ProjectOneActorEvidence(
            event_id="e000",
            actor_posterior={OWNER: 0.7, GUEST: 0.7},
            reference_actor_prior={OWNER: 0.5, GUEST: 0.5},
            evidence_track="controlled_noise",
            evidence_model_id="m",
        )


def test_actor_evidence_has_no_true_actor_field() -> None:
    """Structural, like ``FORBIDDEN_RECORD_FIELDS``: truth cannot be added by accident."""

    forbidden = {"true_actor", "actor_id", "ground_truth", "label"}
    assert not forbidden & set(ProjectOneActorEvidence.__dataclass_fields__)


def test_likelihood_ratios_divide_out_the_shared_prior() -> None:
    """So a channel prior is not multiplied in twice downstream."""

    evidence = ProjectOneActorEvidence(
        event_id="e000",
        actor_posterior={OWNER: 0.5, GUEST: 0.25, UNKNOWN_ACTOR: 0.25},
        reference_actor_prior={OWNER: 0.25, GUEST: 0.25, UNKNOWN_ACTOR: 0.5},
        evidence_track="controlled_noise",
        evidence_model_id="m",
    )
    ratios = evidence.likelihood_ratios()
    assert ratios[OWNER] == pytest.approx(2.0)
    assert ratios[GUEST] == pytest.approx(1.0)
    assert ratios[UNKNOWN_ACTOR] == pytest.approx(0.5)


def test_channel_owner_must_match_the_arm_subject() -> None:
    channel = ProjectOneActorChannel(
        policy=ActorEvidencePolicy.ABSENT,
        owner_id="someone_else",
        support=("someone_else", UNKNOWN_ACTOR),
    )
    with pytest.raises(ValueError, match="does not match the arm"):
        _chain(channel)


# ---------------------------------------------------------------------------
# Fairness: the baselines never had this input
# ---------------------------------------------------------------------------


def test_no_baseline_arm_ever_read_actor_truth() -> None:
    """The baselines are already isolated -- which is why the default is unfair.

    Fails if a baseline starts reading ``actor_id``.  Recorded here because the
    asymmetry is the substantive finding: under ``actor_channel=None`` the
    chain arms hold person truth and the three baselines do not, so a
    chain-versus-baseline gap is partly an information gap.
    """

    records = _stream()
    builders = (
        lambda: CategoricalBOCPDMethod(LOCATIONS),
        lambda: ContextFrequencyMethod(LOCATIONS),
        lambda: PersistenceMethod(LOCATIONS),
    )
    for build in builders:
        report = audit_actor_truth_isolation(
            build,
            records,
            policy=ActorEvidencePolicy.LEGACY_HARD_ACTOR,
            owner_id=OWNER,
        )
        assert report.isolated, report.summary()


def test_build_first_batch_puts_every_arm_in_one_information_regime() -> None:
    channel = _channel(ActorEvidencePolicy.CONTROLLED_NOISE)
    arms = build_first_batch(
        locations=LOCATIONS,
        owner_id=OWNER,
        household_id="h1",
        object_id="cup",
        actor_channel=channel,
    )
    records = _stream()
    for arm in arms:
        report = audit_actor_truth_isolation(
            lambda arm=arm: _rebuilt(arm, channel),
            records,
            policy=ActorEvidencePolicy.CONTROLLED_NOISE,
            owner_id=OWNER,
        )
        assert report.isolated, (arm.name, report.summary())


def _rebuilt(arm, channel):  # type: ignore[no-untyped-def]
    if isinstance(arm, CoreHabitChainMethod):
        return CoreHabitChainMethod(
            name=arm.name,
            locations=LOCATIONS,
            owner_id=OWNER,
            household_id="h1",
            object_id="cup",
            config=arm.config,
            actor_channel=channel,
        )
    return type(arm)(LOCATIONS)


# ---------------------------------------------------------------------------
# Provenance: a result must say how much it was told
# ---------------------------------------------------------------------------


def test_the_policy_travels_with_the_config_hash() -> None:
    """Two arms differing only in actor policy must not share a hash.

    Fails if the channel is recorded beside the config instead of inside it,
    which is how an oracle run gets filed as a method result.
    """

    hashes = {
        policy.value: _chain(_channel(policy)).config_hash()
        for policy in (
            ActorEvidencePolicy.ABSENT,
            ActorEvidencePolicy.CONTROLLED_NOISE,
            ActorEvidencePolicy.ORACLE,
        )
    }
    hashes["legacy"] = _chain(None, allow_legacy_hard_actor=True).config_hash()
    assert len(set(hashes.values())) == len(hashes), hashes


def test_snapshot_reports_the_policy_and_the_masking_count() -> None:
    arm = _chain(_channel(ActorEvidencePolicy.CONTROLLED_NOISE))
    for record in _stream():
        arm.observe(record)
    snapshot = arm.snapshot()
    assert snapshot["actor_evidence_policy"] == ActorEvidencePolicy.CONTROLLED_NOISE.value
    assert snapshot["masked_actor_events"] == len(_stream())


def test_oracle_is_flagged_as_an_upper_bound() -> None:
    """So an oracle number cannot be quoted as a method score by mistake."""

    payload = _channel(ActorEvidencePolicy.ORACLE).config_payload()
    assert payload["is_upper_bound"] is True
    for policy in (ActorEvidencePolicy.ABSENT, ActorEvidencePolicy.CONTROLLED_NOISE):
        assert _channel(policy).config_payload()["is_upper_bound"] is False


def test_permutation_helper_changes_only_the_actor_field() -> None:
    records = _stream()
    permuted = permute_actor_labels(records, owner_id=OWNER)
    for before, after in zip(records, permuted, strict=True):
        assert before.actor_id != after.actor_id
        for name in before.__dataclass_fields__:
            if name == "actor_id":
                continue
            assert getattr(before, name) == getattr(after, name)
