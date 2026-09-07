"""Five-arm Task-7 history-support recovery development study.

The two retained mechanisms are deliberately separable:

* a correction-ready ancestry reservoir preserves pre-resampling prefixes at
  the corrected boundary and replays only the affected suffix; and
* a backward-message checkpoint carries suffix importance contributions for
  already-retained trajectories, so a late factor can be propagated without a
  new suffix rollout.

The combined arm retains both the prefix reservoir and one suffix message per
reservoir entry.  This is development evidence, not an external or paper gate.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from cpswm.system.evaluation_operations import structure_two_backbone_falsifier as backbone
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-task7-history-support-five-arm@0.2-development"


class Task7SupportRecoveryArm(StrEnum):
    RESERVOIR_ONLY = "reservoir_only"
    BACKWARD_MESSAGE_ONLY = "backward_message_only"
    COMBINED = "combined"
    FULL_RERUN_REFERENCE = "full_rerun_reference"
    CURRENT_V04_FAILURE_CONTROL = "current_task_7_v0_4_failure_control"


@dataclass(frozen=True, slots=True)
class CorrectionReadyAncestryReservoir:
    correction_index: int
    particles: tuple[backbone.Particle, ...]
    rng_state: tuple[Any, ...]
    rng_state_sha256: str
    source_stream_sha256: str
    reservoir_sha256: str

    @property
    def unique_prefix_count(self) -> int:
        return len({particle.chain().key for particle in self.particles})

    @property
    def estimated_serialized_bytes(self) -> int:
        return sum(
            len(repr(_particle_payload(particle)).encode("utf-8")) for particle in self.particles
        )


@dataclass(frozen=True, slots=True)
class BackwardMessageEntry:
    source_prefix_key: str
    descendant: backbone.Particle
    original_prefix_log_target: float
    original_suffix_log_message: float
    entry_sha256: str


@dataclass(frozen=True, slots=True)
class BackwardMessageCheckpoint:
    correction_index: int
    messages: tuple[BackwardMessageEntry, ...]
    source_prefix_sha256: str
    source_suffix_sha256: str
    checkpoint_sha256: str

    @property
    def descendants(self) -> tuple[backbone.Particle, ...]:
        return tuple(item.descendant for item in self.messages)

    @property
    def unique_descendant_count(self) -> int:
        return len({particle.chain().key for particle in self.descendants})


def _prefix_chain(chain: backbone.ChainHypothesis, stop: int) -> backbone.ChainHypothesis:
    return backbone.ChainHypothesis(
        gaps=chain.gaps[:stop],
        regime_timeline=chain.regime_timeline[:stop],
        run_lengths=chain.run_lengths[:stop],
    )


def _conditional_suffix_log_target(
    chain: backbone.ChainHypothesis,
    observations: Sequence[backbone.GapObservation],
    *,
    stop: int,
    meter: backbone.CostMeter,
    coupling: float,
) -> tuple[float, float]:
    prefix = _prefix_chain(chain, stop)
    prefix_log_target = backbone.chain_log_target(
        prefix,
        observations[:stop],
        meter,
        relative_probability_coupling_nats=coupling,
    )
    full_log_target = backbone.chain_log_target(
        chain,
        observations,
        meter,
        relative_probability_coupling_nats=coupling,
    )
    return prefix_log_target, full_log_target - prefix_log_target


def _stream_hash(observations: Sequence[backbone.GapObservation]) -> str:
    return content_sha256(backbone._observation_payload(observations))


def _particle_payload(particle: backbone.Particle) -> dict[str, Any]:
    return {
        "chain": particle.chain().key,
        "log_weight": particle.log_weight,
        "boundary": {
            "current": particle.current,
            "retired": list(particle.retired),
            "created": particle.created,
            "run_length": particle.runs[-1] if particle.runs else 0,
        },
        "ancestry": list(particle.ancestry),
    }


def _capture_forward_reservoir(
    scenario: backbone.BackboneScenario,
    *,
    correction_index: int,
    arm: backbone.ArmName,
    budget: int,
    seed: int,
) -> tuple[
    list[backbone.Particle],
    float,
    random.Random,
    backbone.CostMeter,
    CorrectionReadyAncestryReservoir,
    float,
]:
    meter = backbone.CostMeter(arm=arm, particle_count=budget)
    meter.start()
    rng = random.Random(f"{backbone.PROTOCOL_ID}:{scenario.scenario_id}:{arm.value}:{seed}")
    config = backbone.ArmConfiguration.of(arm)
    particles = [
        backbone.Particle(
            gaps=(),
            timeline=(),
            runs=(),
            current="R0",
            retired=(),
            created=0,
            log_weight=0.0,
            blocks={},
            thetas={},
            ancestry=("root",),
        )
        for _ in range(budget)
    ]
    log_evidence = 0.0
    prefix_log_evidence = 0.0
    reservoir_particles: tuple[backbone.Particle, ...] | None = None
    reservoir_rng_state: tuple[Any, ...] | None = None
    for index, observation in enumerate(scenario.observations):
        # Capture before the possibly corrupt observation. Capturing after it
        # cannot restore hypotheses removed by that observation's proposal or
        # resampling step.
        if index == correction_index:
            reservoir_particles = tuple(particle.clone() for particle in particles)
            reservoir_rng_state = rng.getstate()
            prefix_log_evidence = log_evidence
        backbone._step_particles(
            particles,
            observation,
            index,
            config=config,
            rng=rng,
            meter=meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        meter.track_live(len(particles))
        log_weights = [particle.log_weight for particle in particles]
        masses = backbone._normalized_masses(log_weights)
        if (
            index < len(scenario.observations) - 1
            and backbone._effective_sample_size(masses) < len(particles) / 2.0
        ):
            log_evidence += backbone._logsumexp(log_weights) - math.log(len(particles))
            particles = backbone._systematic_resample(particles, masses, rng)
            meter.resample()
    if reservoir_particles is None or reservoir_rng_state is None:
        raise ValueError("Task-7 correction boundary was not observed")
    rng_state_sha256 = content_sha256(reservoir_rng_state)
    payload = {
        "particles": [_particle_payload(particle) for particle in reservoir_particles],
        "rng_state_sha256": rng_state_sha256,
    }
    reservoir = CorrectionReadyAncestryReservoir(
        correction_index=correction_index,
        particles=reservoir_particles,
        rng_state=reservoir_rng_state,
        rng_state_sha256=rng_state_sha256,
        source_stream_sha256=_stream_hash(scenario.observations),
        reservoir_sha256=content_sha256(payload),
    )
    replay_rng = random.Random()
    replay_rng.setstate(reservoir_rng_state)
    return particles, log_evidence, replay_rng, meter, reservoir, prefix_log_evidence


def _corrected_unresolved_log_weight(
    original: Sequence[backbone.GapObservation],
    corrected: Sequence[backbone.GapObservation],
    correction_index: int,
) -> float:
    return (
        backbone.unresolved_log_target(original)
        - backbone._unresolved_observation_log_term(original[correction_index])
        + backbone._unresolved_observation_log_term(corrected[correction_index])
    )


def _apply_correction(
    particles: Sequence[backbone.Particle],
    *,
    original: Sequence[backbone.GapObservation],
    corrected: Sequence[backbone.GapObservation],
    correction_index: int,
    meter: backbone.CostMeter,
) -> None:
    for particle in particles:
        ratio = backbone._apply_fixed_observation_correction(
            particle,
            original[correction_index],
            corrected[correction_index],
            correction_index,
            meter,
        )
        particle.log_weight += ratio
    meter.fixed_gap_reweight_evaluations += len(particles)


def _continue_suffix(
    particles: list[backbone.Particle],
    *,
    scenario: backbone.BackboneScenario,
    observations: Sequence[backbone.GapObservation],
    start_index: int,
    arm: backbone.ArmName,
    rng: random.Random,
    meter: backbone.CostMeter,
    log_evidence: float,
    allow_resampling: bool,
) -> tuple[list[backbone.Particle], float]:
    config = backbone.ArmConfiguration.of(arm)
    for index in range(start_index, len(observations)):
        backbone._step_particles(
            particles,
            observations[index],
            index,
            config=config,
            rng=rng,
            meter=meter,
            relative_probability_coupling_nats=(scenario.relative_probability_coupling_nats),
        )
        meter.track_live(len(particles))
        weights = backbone._normalized_masses([particle.log_weight for particle in particles])
        if (
            allow_resampling
            and index < len(observations) - 1
            and backbone._effective_sample_size(weights) < len(particles) / 2.0
        ):
            log_weights = [particle.log_weight for particle in particles]
            log_evidence += backbone._logsumexp(log_weights) - math.log(len(particles))
            particles = backbone._systematic_resample(particles, weights, rng)
            meter.resample()
    return particles, log_evidence


def _build_backward_checkpoint(
    reservoir: CorrectionReadyAncestryReservoir,
    *,
    scenario: backbone.BackboneScenario,
    correction_index: int,
    arm: backbone.ArmName,
    seed: int,
    precomputed_descendants: Sequence[backbone.Particle] | None = None,
) -> tuple[BackwardMessageCheckpoint, backbone.CostMeter]:
    _verify_reservoir(reservoir, scenario=scenario, correction_index=correction_index)
    descendants = (
        [particle.clone() for particle in precomputed_descendants]
        if precomputed_descendants is not None
        else [particle.clone() for particle in reservoir.particles]
    )
    meter = backbone.CostMeter(arm=arm, particle_count=len(descendants))
    meter.start()
    if precomputed_descendants is None:
        rng = random.Random()
        rng.setstate(reservoir.rng_state)
        descendants, _ = _continue_suffix(
            descendants,
            scenario=scenario,
            observations=scenario.observations,
            start_index=correction_index,
            arm=arm,
            rng=rng,
            meter=meter,
            log_evidence=0.0,
            allow_resampling=False,
        )
    stop = correction_index
    messages: list[BackwardMessageEntry] = []
    for descendant in descendants:
        chain = descendant.chain()
        prefix_log_target, suffix_log_message = _conditional_suffix_log_target(
            chain,
            scenario.observations,
            stop=stop,
            meter=meter,
            coupling=scenario.relative_probability_coupling_nats,
        )
        source_prefix_key = _prefix_chain(chain, stop).key
        entry_payload = {
            "source_prefix_key": source_prefix_key,
            "descendant": _particle_payload(descendant),
            "original_prefix_log_target": prefix_log_target,
            "original_suffix_log_message": suffix_log_message,
        }
        messages.append(
            BackwardMessageEntry(
                source_prefix_key=source_prefix_key,
                descendant=descendant,
                original_prefix_log_target=prefix_log_target,
                original_suffix_log_message=suffix_log_message,
                entry_sha256=content_sha256(entry_payload),
            )
        )
    meter.stop()
    # Bind the message to the actual pre-correction observation prefix.  The
    # reservoir has its own independent hash; conflating the two would allow a
    # checkpoint generated against a stale prefix stream to pass verification.
    source_prefix_sha256 = _stream_hash(scenario.observations[:correction_index])
    source_suffix_sha256 = _stream_hash(scenario.observations[correction_index:])
    payload = {
        "correction_index": correction_index,
        "source_prefix_sha256": source_prefix_sha256,
        "source_suffix_sha256": source_suffix_sha256,
        "messages": [
            {
                "source_prefix_key": item.source_prefix_key,
                "descendant": _particle_payload(item.descendant),
                "original_prefix_log_target": item.original_prefix_log_target,
                "original_suffix_log_message": item.original_suffix_log_message,
                "entry_sha256": item.entry_sha256,
            }
            for item in messages
        ],
    }
    return (
        BackwardMessageCheckpoint(
            correction_index=correction_index,
            messages=tuple(messages),
            source_prefix_sha256=source_prefix_sha256,
            source_suffix_sha256=source_suffix_sha256,
            checkpoint_sha256=content_sha256(payload),
        ),
        meter,
    )


def _verify_reservoir(
    reservoir: CorrectionReadyAncestryReservoir,
    *,
    scenario: backbone.BackboneScenario,
    correction_index: int,
) -> None:
    if reservoir.correction_index != correction_index:
        raise ValueError("Task-7 reservoir correction boundary differs")
    if reservoir.source_stream_sha256 != _stream_hash(scenario.observations):
        raise ValueError("Task-7 reservoir source stream binding is stale")
    if content_sha256(reservoir.rng_state) != reservoir.rng_state_sha256:
        raise ValueError("Task-7 reservoir RNG checkpoint content hash does not match")
    expected = content_sha256(
        {
            "particles": [_particle_payload(particle) for particle in reservoir.particles],
            "rng_state_sha256": reservoir.rng_state_sha256,
        }
    )
    if expected != reservoir.reservoir_sha256:
        raise ValueError("Task-7 reservoir particle content hash does not match")


def _apply_backward_messages(
    checkpoint: BackwardMessageCheckpoint,
    *,
    scenario: backbone.BackboneScenario,
    corrected: Sequence[backbone.GapObservation],
    meter: backbone.CostMeter,
) -> list[backbone.Particle]:
    checkpoint_payload = {
        "correction_index": checkpoint.correction_index,
        "source_prefix_sha256": checkpoint.source_prefix_sha256,
        "source_suffix_sha256": checkpoint.source_suffix_sha256,
        "messages": [
            {
                "source_prefix_key": item.source_prefix_key,
                "descendant": _particle_payload(item.descendant),
                "original_prefix_log_target": item.original_prefix_log_target,
                "original_suffix_log_message": item.original_suffix_log_message,
                "entry_sha256": item.entry_sha256,
            }
            for item in checkpoint.messages
        ],
    }
    if content_sha256(checkpoint_payload) != checkpoint.checkpoint_sha256:
        raise ValueError("backward message checkpoint content hash does not match")
    if checkpoint.source_suffix_sha256 != _stream_hash(
        scenario.observations[checkpoint.correction_index :]
    ):
        raise ValueError("backward message suffix binding is stale")
    if checkpoint.source_prefix_sha256 != _stream_hash(
        scenario.observations[: checkpoint.correction_index]
    ):
        raise ValueError("backward message prefix binding is stale")
    stop = checkpoint.correction_index
    repaired: list[backbone.Particle] = []
    for item in checkpoint.messages:
        expected_entry_hash = content_sha256(
            {
                "source_prefix_key": item.source_prefix_key,
                "descendant": _particle_payload(item.descendant),
                "original_prefix_log_target": item.original_prefix_log_target,
                "original_suffix_log_message": item.original_suffix_log_message,
            }
        )
        if expected_entry_hash != item.entry_sha256:
            raise ValueError("backward message entry content hash does not match")
        particle = item.descendant.clone()
        prefix_log_target, suffix_log_message = _conditional_suffix_log_target(
            particle.chain(),
            corrected,
            stop=stop,
            meter=meter,
            coupling=scenario.relative_probability_coupling_nats,
        )
        original_total = item.original_prefix_log_target + item.original_suffix_log_message
        corrected_total = prefix_log_target + suffix_log_message
        particle.log_weight += corrected_total - original_total
        repaired.append(particle)
    meter.fixed_gap_reweight_evaluations += len(repaired)
    return repaired


def _custom_support_arm(
    scenario: backbone.BackboneScenario,
    *,
    recovery_arm: Task7SupportRecoveryArm,
    correction_index: int,
    budget: int,
    seed: int,
) -> backbone.ArmResult:
    particle_arm = backbone.ArmName.ADAPTIVE_TYPED_RBPF
    corrected = backbone.repair_observation(scenario, correction_index)
    (
        final_particles,
        final_evidence,
        forward_rng,
        initial_meter,
        reservoir,
        prefix_evidence,
    ) = _capture_forward_reservoir(
        scenario,
        correction_index=correction_index,
        arm=particle_arm,
        budget=budget,
        seed=seed,
    )
    _verify_reservoir(
        reservoir,
        scenario=scenario,
        correction_index=correction_index,
    )
    initial_meter.stop()
    repair_meter = backbone.CostMeter(arm=particle_arm, particle_count=budget)
    repair_meter.start()
    message_checkpoint: BackwardMessageCheckpoint | None = None

    if recovery_arm is Task7SupportRecoveryArm.RESERVOIR_ONLY:
        particles = [particle.clone() for particle in reservoir.particles]
        evidence = prefix_evidence
        particles, evidence = _continue_suffix(
            particles,
            scenario=scenario,
            observations=corrected.observations,
            start_index=correction_index,
            arm=particle_arm,
            rng=forward_rng,
            meter=repair_meter,
            log_evidence=evidence,
            allow_resampling=True,
        )
        ancestry_window_length = len(corrected.observations) - correction_index
        repair_mode = "pre_correction_reservoir_boundary_replay"
    elif recovery_arm is Task7SupportRecoveryArm.BACKWARD_MESSAGE_ONLY:
        message_checkpoint, message_meter = _build_backward_checkpoint(
            reservoir,
            scenario=scenario,
            correction_index=correction_index,
            arm=particle_arm,
            seed=seed,
            precomputed_descendants=final_particles,
        )
        initial_meter = backbone._combine_cost_meters(initial_meter, message_meter)
        particles = _apply_backward_messages(
            message_checkpoint,
            scenario=scenario,
            corrected=corrected.observations,
            meter=repair_meter,
        )
        evidence = final_evidence
        ancestry_window_length = 0
        repair_mode = "surviving_support_conditional_backward_message"
    elif recovery_arm is Task7SupportRecoveryArm.COMBINED:
        message_checkpoint, message_meter = _build_backward_checkpoint(
            reservoir,
            scenario=scenario,
            correction_index=correction_index,
            arm=particle_arm,
            seed=seed,
        )
        initial_meter = backbone._combine_cost_meters(initial_meter, message_meter)
        particles = _apply_backward_messages(
            message_checkpoint,
            scenario=scenario,
            corrected=corrected.observations,
            meter=repair_meter,
        )
        evidence = prefix_evidence
        ancestry_window_length = 0
        repair_mode = "reservoir_plus_conditional_backward_message"
    else:
        raise ValueError(f"unsupported custom Task-7 arm: {recovery_arm.value}")

    result = backbone._finalize(
        particles,
        evidence,
        corrected.observations,
        repair_meter,
        unresolved_log_weight=_corrected_unresolved_log_weight(
            scenario.observations, corrected.observations, correction_index
        ),
    )
    result = backbone._with_lifecycle_cost(
        result,
        initial_meter=initial_meter,
        repair_meter=repair_meter,
        ancestry_window_length=ancestry_window_length,
    )
    result.cost.update(
        {
            "repair_mode": repair_mode,
            "support_recovery_arm": recovery_arm.value,
            "reservoir_particle_count": len(reservoir.particles),
            "reservoir_unique_prefix_count": reservoir.unique_prefix_count,
            "reservoir_estimated_serialized_bytes": reservoir.estimated_serialized_bytes,
            "reservoir_sha256": reservoir.reservoir_sha256,
            "backward_message_checkpoint_sha256": (
                "not_applicable"
                if message_checkpoint is None
                else message_checkpoint.checkpoint_sha256
            ),
            "backward_message_descendant_count": (
                0 if message_checkpoint is None else len(message_checkpoint.descendants)
            ),
            "backward_message_unique_descendant_count": (
                0 if message_checkpoint is None else message_checkpoint.unique_descendant_count
            ),
            "full_prefix_rerun_after_correction": False,
        }
    )
    return result


def run_task7_support_recovery_arm(
    scenario: backbone.BackboneScenario,
    *,
    recovery_arm: Task7SupportRecoveryArm,
    correction_index: int,
    budget: int,
    seed: int,
    v04_window_length: int = 3,
    v04_sweeps: int = 2,
) -> backbone.ArmResult:
    if recovery_arm in {
        Task7SupportRecoveryArm.RESERVOIR_ONLY,
        Task7SupportRecoveryArm.BACKWARD_MESSAGE_ONLY,
        Task7SupportRecoveryArm.COMBINED,
    }:
        return _custom_support_arm(
            scenario,
            recovery_arm=recovery_arm,
            correction_index=correction_index,
            budget=budget,
            seed=seed,
        )
    if recovery_arm is Task7SupportRecoveryArm.FULL_RERUN_REFERENCE:
        result = backbone.run_late_correction(
            scenario,
            treatment=backbone.CorrectionTreatment.FULL_RERUN,
            correction_index=correction_index,
            arm=backbone.ArmName.ADAPTIVE_TYPED_RBPF,
            budget=budget,
            seed=seed,
        )
    elif recovery_arm is Task7SupportRecoveryArm.CURRENT_V04_FAILURE_CONTROL:
        result = backbone.run_late_correction(
            scenario,
            treatment=backbone.CorrectionTreatment.LOCAL_REJUVENATION,
            correction_index=correction_index,
            arm=backbone.ArmName.ADAPTIVE_TYPED_RBPF,
            budget=budget,
            seed=seed,
            rejuvenation_window_length=v04_window_length,
            rejuvenation_sweeps=v04_sweeps,
        )
    else:
        raise ValueError(f"unknown Task-7 recovery arm: {recovery_arm.value}")
    result.cost.update({"support_recovery_arm": recovery_arm.value})
    return result


def _arm_row(
    arm: Task7SupportRecoveryArm,
    result: backbone.ArmResult,
    reference: backbone.ArmResult,
    *,
    scenario: backbone.BackboneScenario,
    corrected_observations: Sequence[backbone.GapObservation],
    correction_index: int,
) -> dict[str, Any]:
    beliefs = backbone.task7_belief_marginals(result, correction_index)
    reference_beliefs = backbone.task7_belief_marginals(reference, correction_index)
    distances = {
        axis: backbone.marginal_distance(reference_beliefs[axis], beliefs[axis])
        for axis in reference_beliefs
    }
    actions = backbone.result_embodied_action_posterior(result, corrected_observations)
    reference_actions = backbone.result_embodied_action_posterior(reference, corrected_observations)
    selected = backbone._task7_bayes_action_key(actions)
    selected_reference = backbone._task7_bayes_action_key(reference_actions)
    return {
        "arm": arm.value,
        "max_belief_axis_tv": max(distances.values()),
        "belief_axis_tv": distances,
        "action_distribution_tv": backbone.action_posterior_distance(reference_actions, actions),
        "selected_action_matches_reference": (
            selected is not None and selected == selected_reference
        ),
        "owner_contamination": backbone.owner_contamination(
            result, scenario.truth, correction_index
        ),
        "unresolved_probability": result.posterior.get(backbone.UNRESOLVED_KEY, 0.0),
        "support_size": len(result.support),
        "marginal_elementary_likelihood_evaluations": int(
            result.cost["marginal_elementary_likelihood_evaluations"]
        ),
        "initial_elementary_likelihood_evaluations": int(
            result.cost["initial_elementary_likelihood_evaluations"]
        ),
        "repair_mode": str(result.cost.get("repair_mode", arm.value)),
        "reservoir_unique_prefix_count": int(result.cost.get("reservoir_unique_prefix_count", 0)),
        "backward_message_unique_descendant_count": int(
            result.cost.get("backward_message_unique_descendant_count", 0)
        ),
    }


def run_task7_support_recovery_five_arm_study(
    *,
    scenario_seeds: Sequence[int],
    replicate_seeds: Sequence[int],
    gaps: int = 12,
    correction_index: int = 2,
    budget: int = 384,
    v04_window_length: int = 3,
    v04_sweeps: int = 2,
) -> dict[str, Any]:
    if not scenario_seeds or not replicate_seeds:
        raise ValueError("Task-7 five-arm study requires non-empty seed sets")
    rows: list[dict[str, Any]] = []
    for scenario_seed in scenario_seeds:
        for ambiguity in (False, True):
            for delayed in (False, True):
                for open_world in (False, True):
                    for short_regime in (False, True):
                        scenario = backbone.build_scenario(
                            gaps=gaps,
                            seed=int(scenario_seed),
                            high_attribution_ambiguity=ambiguity,
                            adverse_delayed_feedback=delayed,
                            open_world_actor=open_world,
                            short_regime=short_regime,
                            corrupt_index=correction_index,
                        )
                        corrected = backbone.repair_observation(scenario, correction_index)
                        for replicate_seed in replicate_seeds:
                            reference = run_task7_support_recovery_arm(
                                scenario,
                                recovery_arm=(Task7SupportRecoveryArm.FULL_RERUN_REFERENCE),
                                correction_index=correction_index,
                                budget=budget,
                                seed=int(replicate_seed),
                                v04_window_length=v04_window_length,
                                v04_sweeps=v04_sweeps,
                            )
                            for recovery_arm in Task7SupportRecoveryArm:
                                result = (
                                    reference
                                    if recovery_arm is Task7SupportRecoveryArm.FULL_RERUN_REFERENCE
                                    else run_task7_support_recovery_arm(
                                        scenario,
                                        recovery_arm=recovery_arm,
                                        correction_index=correction_index,
                                        budget=budget,
                                        seed=int(replicate_seed),
                                        v04_window_length=v04_window_length,
                                        v04_sweeps=v04_sweeps,
                                    )
                                )
                                rows.append(
                                    {
                                        "scenario_id": scenario.scenario_id,
                                        "scenario_factors": {
                                            "high_attribution_ambiguity": ambiguity,
                                            "adverse_delayed_feedback": delayed,
                                            "open_world_actor": open_world,
                                            "short_regime": short_regime,
                                        },
                                        "replicate_seed": int(replicate_seed),
                                        **_arm_row(
                                            recovery_arm,
                                            result,
                                            reference,
                                            scenario=scenario,
                                            corrected_observations=(corrected.observations),
                                            correction_index=correction_index,
                                        ),
                                    }
                                )
    summaries: dict[str, dict[str, Any]] = {}
    for arm in Task7SupportRecoveryArm:
        arm_rows = [row for row in rows if row["arm"] == arm.value]
        summaries[arm.value] = {
            "row_count": len(arm_rows),
            "mean_max_belief_axis_tv": sum(float(row["max_belief_axis_tv"]) for row in arm_rows)
            / len(arm_rows),
            "worst_max_belief_axis_tv": max(float(row["max_belief_axis_tv"]) for row in arm_rows),
            "mean_action_distribution_tv": sum(
                float(row["action_distribution_tv"]) for row in arm_rows
            )
            / len(arm_rows),
            "selected_action_match_rate": sum(
                bool(row["selected_action_matches_reference"]) for row in arm_rows
            )
            / len(arm_rows),
            "mean_owner_contamination": sum(float(row["owner_contamination"]) for row in arm_rows)
            / len(arm_rows),
            "mean_marginal_elementary_likelihood_evaluations": sum(
                int(row["marginal_elementary_likelihood_evaluations"]) for row in arm_rows
            )
            / len(arm_rows),
            "mean_initial_elementary_likelihood_evaluations": sum(
                int(row["initial_elementary_likelihood_evaluations"]) for row in arm_rows
            )
            / len(arm_rows),
        }
    return {
        "protocol_id": PROTOCOL_ID,
        "evidence_status": (
            "D0 development five-arm attribution; no independent custody or external-validity claim"
        ),
        "design": {
            "scenario_seeds": [int(seed) for seed in scenario_seeds],
            "replicate_seeds": [int(seed) for seed in replicate_seeds],
            "factor_cells_per_scenario_seed": 16,
            "gaps": gaps,
            "correction_index": correction_index,
            "particle_budget": budget,
            "reservoir_budget": budget,
            "backward_message_descendants_per_reservoir_entry": 1,
            "v04_window_length": v04_window_length,
            "v04_sweeps": v04_sweeps,
        },
        "required_arms": [arm.value for arm in Task7SupportRecoveryArm],
        "summaries": summaries,
        "rows": rows,
        "claim_boundary": (
            "A development win can motivate a separately frozen confirmation gate; "
            "it cannot rewrite the immutable Task-7 v0.4 failure or authorize the paper claim."
        ),
    }


__all__ = [
    "PROTOCOL_ID",
    "BackwardMessageCheckpoint",
    "CorrectionReadyAncestryReservoir",
    "Task7SupportRecoveryArm",
    "run_task7_support_recovery_arm",
    "run_task7_support_recovery_five_arm_study",
]
