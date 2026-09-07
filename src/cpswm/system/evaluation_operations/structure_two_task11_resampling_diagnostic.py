"""Task 11 full-budget resampling diagnostic with raw and fresh-source gates."""
# ruff: noqa: E501

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import platform
import random
import stat
import subprocess
import sys
import time
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import distributions
from pathlib import Path
from typing import Any, Final

from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (
    UNRESOLVED_KEY,
    Actor,
    ArmConfiguration,
    ArmName,
    BackboneScenario,
    CallerRole,
    Cause,
    ChainHypothesis,
    CostMeter,
    GapHypothesis,
    Instance,
    Mechanism,
    Particle,
    RegimeMove,
    _logsumexp,
    _step_particles,
    action_posterior_distance,
    chain_embodied_action,
    exact_decision_summary,
    registered_scenarios,
    unresolved_log_target,
)

EVIDENCE_STATUS: Final = "UNAUTHENTICATED_DIAGNOSTIC"
AUTHORITY: Final = "LOCAL_DIAGNOSTIC_ONLY"
PROTOCOL_ID: Final = "structure-two-backbone-resampling-task-11@0.3"
TRACE_SCHEMA: Final = "structure-two-task11-raw-trace@0.3"
SUMMARY_SCHEMA: Final = "structure-two-task11-recomputed-results@0.3"
MANIFEST_SCHEMA: Final = "structure-two-task11-evidence-manifest@0.4"
RUN_ID_DOMAIN: Final = "cpswm.structure_two.task11.local_diagnostic.v3"
BASE_COMMIT: Final = "ae27b8505c9f6abae4e0584a1f5a0ce7205087ec"
FINAL_INVOCATION_ID: Final = (
    "task11-full-budget-diagnostic-2026-09-06-adversarial-rerun-source-bound"
)
OUTPUT_RELATIVE: Final = (
    "benchmarks/structure_two/task11_resampling_full_budget_2026_09_06_adversarial_rerun"
)
RECOVERY_RAW_RELATIVE: Final = (
    ".checkpoint_quarantine/task11_failed_2026-09-06_evaluator-support/raw_traces"
)
VALIDATION_REPLICATE_SEEDS: Final = (101,)
CONFIRMATORY_REPLICATE_SEEDS: Final = (202, 303)
ALL_REPLICATE_SEEDS: Final = VALIDATION_REPLICATE_SEEDS + CONFIRMATORY_REPLICATE_SEEDS
GAP_CONTEXTS: Final = {"G1": (1, (11, 23, 37, 41, 53)), "G2": (2, (11,))}
TEST_CONTEXTS: Final = {"G3_TEST": (3, (1,))}
CONTEXT_BUDGETS: Final = {
    "G1": (8, 16, 24, 48, 96, 384, 1536),
    "G2": (24, 96, 384),
}
ALGORITHMS: Final = (
    "no_resampling",
    "systematic",
    "stratified",
    "residual",
    "multinomial_negative_control",
)
ESS_THRESHOLDS: Final = (0.25, 0.5, 0.75)
NEGATIVE_CONTROL: Final = "multinomial_negative_control"
SOURCE_RELATIVE_PATHS: Final = (
    "src/cpswm/system/evaluation_operations/structure_two_task11_resampling_diagnostic.py",
    "apps/evaluation_runner/run_structure_two_task11_resampling_diagnostic.py",
    "apps/evaluation_runner/recompute_structure_two_task11_resampling_diagnostic.py",
    "tests/test_structure_two_task11_task12_runtime.py",
)
COMPONENT_INVENTORY: Final = {
    role: "src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"
    for role in (
        "backbone_falsifier",
        "scenario_generator",
        "proposal",
        "weighting",
        "action_evaluator",
        "exact_evaluator",
    )
}
FROZEN_RELATIVE_PATHS: Final = (
    "configs/project_two_experiments/structure_two_backbone_open_tasks_v0_1.json",
    "src/cpswm/system/evaluation_operations/structure_two_backbone_open_task_protocols.py",
    "tests/test_structure_two_backbone_open_task_protocols.py",
    "docs/结构二/方向结构二_Tasks10-13_P5回执DAG与唯一七算子授权协议_v1.0.md",
    "configs/project_two_experiments/structure_two_task10_particle_budget_v0_1.json",
    "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/task_10_budget_sweep_g1.json",
    "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/task_10_budget_sweep_g2.json",
)
KNOWN_FROZEN_SHA256: Final = {
    FROZEN_RELATIVE_PATHS[0]: "50ce43117414cb10da300de1a7c605516175057a9a24dfefbb4a674888fb6a2b",
    FROZEN_RELATIVE_PATHS[1]: "a6cfbaa055044c0cb7cc6295e143fba909b9537ec822ae206adaacc053350e89",
    FROZEN_RELATIVE_PATHS[2]: "c19d19412dddb96651106b9c95f77285dfa3be02b143fafd9e5acadea685b719",
    FROZEN_RELATIVE_PATHS[3]: "0dfe27664ea38dd4c96090bf7a0aa3aa440d276e575f0ff41c45d1964684406f",
    FROZEN_RELATIVE_PATHS[4]: "331782935673ccd4d9fa8a8cda2015078d828bd64001882e57598d651ee027dc",
    FROZEN_RELATIVE_PATHS[5]: "dcad78514018f27ba8b57c02d3429d6a66aab68e6bae347b2ddc24d9536c2eef",
    FROZEN_RELATIVE_PATHS[6]: "26b3fafaedd94f2e9852869887a662b10f9c67441d740d2f2fb8cab3398f1798",
}


class Task11VerificationError(ValueError):
    pass


class FormalTask11UnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Policy:
    algorithm: str
    ess_fraction: float | None

    def __post_init__(self) -> None:
        if self.algorithm not in ALGORITHMS:
            raise ValueError("unknown resampling algorithm")
        if self.algorithm == "no_resampling" and self.ess_fraction is not None:
            raise ValueError("no_resampling cannot have a threshold")
        if self.algorithm != "no_resampling" and self.ess_fraction not in ESS_THRESHOLDS:
            raise ValueError("invalid ESS threshold")

    @property
    def key(self) -> str:
        return (
            self.algorithm
            if self.ess_fraction is None
            else f"{self.algorithm}@ess={self.ess_fraction:g}"
        )

    def as_dict(self) -> dict[str, object]:
        return {"algorithm": self.algorithm, "ess_fraction": self.ess_fraction, "key": self.key}


POLICIES: Final = (
    Policy("no_resampling", None),
    *(Policy(name, threshold) for name in ALGORITHMS[1:] for threshold in ESS_THRESHOLDS),
)
_EXACT_POSTERIOR_DIGEST_CACHE: dict[str, str] = {}


@dataclass(slots=True)
class TrackedParticle:
    particle: Particle
    particle_id: str
    parent_particle_id: str | None
    root_ancestor_id: str


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise Task11VerificationError(f"not a regular file: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    return sha256_bytes(_read_regular_file(path))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def working_tree_status(root: Path) -> list[str]:
    value = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    return value.splitlines() if value else []


def verify_clean_source_checkout(root: Path) -> str:
    if working_tree_status(root):
        raise Task11VerificationError("source execution requires a clean tracked/untracked tree")
    return _git(root, "rev-parse", "HEAD")


def verify_frozen_inputs(root: Path) -> dict[str, str]:
    actual = {path: sha256_file(root / path) for path in KNOWN_FROZEN_SHA256}
    if actual != KNOWN_FROZEN_SHA256:
        raise Task11VerificationError("frozen input drift")
    task10 = json.loads(_read_regular_file(root / FROZEN_RELATIVE_PATHS[4]))
    if task10.get("formal_task_10_passed") is not False:
        raise Task11VerificationError("Task 10 cannot report a formal pass")
    if task10.get("selection_authority") != "NONE_DIAGNOSTIC_CURVE_ONLY":
        raise Task11VerificationError("unexpected Task 10 selection authority")
    for context, (gaps, seeds) in GAP_CONTEXTS.items():
        design = task10["designs"][context.lower()]
        if design["gaps"] != gaps or tuple(design["scenario_seeds"]) != seeds:
            raise Task11VerificationError(f"Task 10 {context} scenario grid drift")
        if tuple(design["budgets"]) != CONTEXT_BUDGETS[context]:
            raise Task11VerificationError(f"Task 10 {context} budget grid drift")
        if tuple(design["replicate_seeds"]) != ALL_REPLICATE_SEEDS:
            raise Task11VerificationError(f"Task 10 {context} replicate grid drift")
    return actual


def normalized_weights(log_weights: Sequence[float]) -> list[float]:
    if not log_weights or any(math.isnan(x) or x == math.inf for x in log_weights):
        raise ValueError("invalid log weights")
    finite = [x for x in log_weights if math.isfinite(x)]
    if not finite:
        raise ValueError("no finite log weights")
    pivot = max(finite)
    masses = [math.exp(x - pivot) if math.isfinite(x) else 0.0 for x in log_weights]
    result = [mass / sum(masses) for mass in masses]
    if not math.isclose(sum(result), 1.0, abs_tol=1e-12):
        raise ValueError("weights not normalized")
    return result


def effective_sample_size(weights: Sequence[float]) -> float:
    if not weights or any(not math.isfinite(x) or x < 0 for x in weights):
        raise ValueError("invalid ESS weights")
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-12):
        raise ValueError("ESS weights not normalized")
    return 1.0 / sum(x * x for x in weights)


def threshold_decision(
    *, ess: float, particle_count: int, ess_fraction: float | None, is_final_step: bool
) -> dict[str, bool]:
    threshold = None if ess_fraction is None else ess_fraction * particle_count
    below = threshold is not None and ess < threshold
    return {
        "below_threshold": below,
        "resampling_performed": below and not is_final_step,
        "final_step_blocked": below and is_final_step,
    }


def _inverse_cdf(weights: Sequence[float], positions: Sequence[float]) -> list[int]:
    cumulative, total = [], 0.0
    for weight in weights:
        total += weight
        cumulative.append(total)
    cumulative[-1] = 1.0
    return [min(bisect_left(cumulative, value), len(weights) - 1) for value in positions]


def resampling_indices(
    weights: Sequence[float], algorithm: str, rng: random.Random
) -> tuple[list[int], dict[str, object]]:
    checked, size = list(weights), len(weights)
    effective_sample_size(checked)
    if algorithm == "systematic":
        offset = rng.random() / size
        positions = [offset + index / size for index in range(size)]
        return _inverse_cdf(checked, positions), {"uniforms": [offset], "positions": positions}
    if algorithm == "stratified":
        uniforms = [rng.random() for _ in range(size)]
        positions = [(index + uniforms[index]) / size for index in range(size)]
        return _inverse_cdf(checked, positions), {"uniforms": uniforms, "positions": positions}
    if algorithm == "multinomial_negative_control":
        uniforms = [rng.random() for _ in range(size)]
        return _inverse_cdf(checked, uniforms), {"uniforms": uniforms, "positions": uniforms}
    if algorithm == "residual":
        counts = [math.floor(size * value) for value in checked]
        selected = [index for index, count in enumerate(counts) for _ in range(count)]
        remainder = size - len(selected)
        residual_weights: list[float] = []
        residual_uniforms: list[float] = []
        if remainder:
            residual = [size * value - count for value, count in zip(checked, counts, strict=True)]
            residual_weights = [value / sum(residual) for value in residual]
            residual_uniforms = [rng.random() for _ in range(remainder)]
            selected.extend(_inverse_cdf(residual_weights, residual_uniforms))
        rng.shuffle(selected)
        return selected, {
            "deterministic_counts": counts,
            "residual_weights": residual_weights,
            "uniforms": residual_uniforms,
        }
    raise ValueError("not a resampling algorithm")


def _scenario_input(scenario: BackboneScenario) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "gaps": scenario.gaps,
        "high_attribution_ambiguity": scenario.high_attribution_ambiguity,
        "adverse_delayed_feedback": scenario.adverse_delayed_feedback,
        "open_world_actor": scenario.open_world_actor,
        "short_regime": scenario.short_regime,
        "corrupt_index": scenario.corrupt_index,
        "relative_probability_coupling_nats": scenario.relative_probability_coupling_nats,
        "observations": [
            {
                "observed_mechanism": x.observed_mechanism.value,
                "observed_giver": x.observed_giver.value,
                "observed_receiver": x.observed_receiver.value,
                "observed_instance": x.observed_instance.value,
                "observed_cause": x.observed_cause.value,
                "observed_regime_change": x.observed_regime_change,
                "placement_bin": x.placement_bin,
                "placement_value": x.placement_value,
                "mechanism_reliability": x.mechanism_reliability,
                "actor_reliability": x.actor_reliability,
                "instance_reliability": x.instance_reliability,
                "cause_reliability": x.cause_reliability,
                "regime_reliability": x.regime_reliability,
            }
            for x in scenario.observations
        ],
    }


def _unresolved_probability(log_evidence: float, observations: Sequence[object]) -> float:
    target = unresolved_log_target(observations)  # type: ignore[arg-type]
    pivot = max(log_evidence, target)
    return math.exp(target - pivot) / (math.exp(log_evidence - pivot) + math.exp(target - pivot))


def _particle_has_unknown(particle: Particle) -> bool:
    return any(
        gap.giver is Actor.UNKNOWN
        or gap.receiver is Actor.UNKNOWN
        or gap.instance is Instance.UNKNOWN
        for gap in particle.gaps
    )


def _chain_has_unknown(chain: ChainHypothesis) -> bool:
    return any(
        gap.giver is Actor.UNKNOWN
        or gap.receiver is Actor.UNKNOWN
        or gap.instance is Instance.UNKNOWN
        for gap in chain.gaps
    )


def _particle_snapshot(
    tracked: Sequence[TrackedParticle], weights: Sequence[float]
) -> list[dict[str, object]]:
    return [
        {
            "particle_id": item.particle_id,
            "parent_particle_id": item.parent_particle_id,
            "root_ancestor_id": item.root_ancestor_id,
            "chain_key": item.particle.chain().key,
            "normalized_weight": weight,
            "log_weight": item.particle.log_weight,
            "unknown_support": _particle_has_unknown(item.particle),
        }
        for item, weight in zip(tracked, weights, strict=True)
    ]


def _compact_snapshots(steps: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    """Deduplicate immutable decision-point snapshots while retaining every raw field."""
    table: dict[str, Any] = {}
    digest_to_reference: dict[str, str] = {}
    for step in steps:
        for field in ("particles_before", "particles_after"):
            rows = step[field]
            digest = canonical_sha256(rows)
            reference = digest_to_reference.get(digest)
            if reference is None:
                reference = f"snapshot-{len(table):02d}"
                digest_to_reference[digest] = reference
                table[reference] = rows
            step[field] = reference
    return table, str(steps[-1]["particles_after"])


def _resolve_snapshot(trace: Mapping[str, Any], reference: object) -> list[Mapping[str, Any]]:
    table = trace.get("particle_snapshots")
    if not isinstance(reference, str) or not isinstance(table, Mapping):
        raise Task11VerificationError("snapshot reference/table missing")
    rows = table.get(reference)
    if not isinstance(rows, list):
        raise Task11VerificationError("snapshot reference unresolved")
    return rows


def _chain_payload(chain: ChainHypothesis) -> dict[str, object]:
    return {
        "gaps": [
            {
                "mechanism": gap.mechanism.value,
                "giver": gap.giver.value,
                "receiver": gap.receiver.value,
                "instance": gap.instance.value,
                "cause": gap.cause.value,
                "regime_move": gap.regime_move.value,
                "regime_target": gap.regime_target,
            }
            for gap in chain.gaps
        ],
        "regime_timeline": list(chain.regime_timeline),
        "run_lengths": list(chain.run_lengths),
    }


def _chain_from_payload(payload: Mapping[str, Any]) -> ChainHypothesis:
    return ChainHypothesis(
        gaps=tuple(
            GapHypothesis(
                Mechanism(x["mechanism"]),
                Actor(x["giver"]),
                Actor(x["receiver"]),
                Instance(x["instance"]),
                Cause(x["cause"]),
                RegimeMove(x["regime_move"]),
                x["regime_target"],
            )
            for x in payload["gaps"]
        ),
        regime_timeline=tuple(payload["regime_timeline"]),
        run_lengths=tuple(int(x) for x in payload["run_lengths"]),
    )


def _counter_snapshot(meter: CostMeter) -> dict[str, int]:
    return {
        "elementary_likelihood_evaluations": meter.elementary_likelihood_evaluations,
        "proposal_generation_evaluations": meter.proposal_generation_evaluations,
        "analytic_block_updates": meter.analytic_block_updates,
        "resampling_events": meter.resampling_events,
    }


def _execution_id(
    invocation_id: str,
    *,
    context: str,
    scenario_id: str,
    replicate_seed: int,
    budget: int,
    policy_key: str,
) -> str:
    return canonical_sha256(
        {
            "domain": RUN_ID_DOMAIN,
            "invocation_id": invocation_id,
            "context": context,
            "scenario_id": scenario_id,
            "replicate_seed": replicate_seed,
            "budget": budget,
            "policy_key": policy_key,
        }
    )


def run_approximate_trace(
    scenario: BackboneScenario,
    *,
    context: str,
    replicate_seed: int,
    budget: int,
    policy: Policy,
    invocation_id: str,
) -> tuple[dict[str, Any], dict[str, Particle]]:
    """Run one deployable arm. Exact truth is intentionally not an argument."""
    unit_test = invocation_id.startswith("task11-unit-")
    designs = {**GAP_CONTEXTS, **(TEST_CONTEXTS if unit_test else {})}
    if context not in designs or scenario.gaps != designs[context][0]:
        raise ValueError("scenario/context mismatch")
    if not unit_test and budget not in CONTEXT_BUDGETS[context]:
        raise ValueError("budget outside frozen grid")
    if replicate_seed not in ALL_REPLICATE_SEEDS and not unit_test:
        raise ValueError("replicate seed outside frozen cluster")
    split = "validation" if replicate_seed in VALIDATION_REPLICATE_SEEDS else "confirmatory"
    execution_id = _execution_id(
        invocation_id,
        context=context,
        scenario_id=scenario.scenario_id,
        replicate_seed=replicate_seed,
        budget=budget,
        policy_key=policy.key,
    )
    proposal_seed = (
        f"{PROTOCOL_ID}:proposal:{context}:{scenario.scenario_id}:{budget}:{replicate_seed}"
    )
    resampling_seed = f"{PROTOCOL_ID}:resampling:{context}:{scenario.scenario_id}:{budget}:{replicate_seed}:{policy.key}"
    proposal_rng, resampling_rng = random.Random(proposal_seed), random.Random(resampling_seed)
    started_at, started = datetime.now(UTC).isoformat(), time.perf_counter()
    meter = CostMeter(arm=ArmName.ADAPTIVE_TYPED_RBPF, particle_count=budget)
    meter.start()
    tracked = [
        TrackedParticle(
            Particle(
                gaps=(),
                timeline=(),
                runs=(),
                current="R0",
                retired=(),
                created=0,
                log_weight=0.0,
                blocks={},
                thetas={},
                ancestry=(f"root-{i:04d}",),
            ),
            f"root-{i:04d}",
            None,
            f"root-{i:04d}",
        )
        for i in range(budget)
    ]
    steps: list[dict[str, Any]] = []
    complete_chain_registry: dict[str, ChainHypothesis] = {}
    accumulated = 0.0
    for step_index, observation in enumerate(scenario.observations):
        counters_before = _counter_snapshot(meter)
        _step_particles(
            [item.particle for item in tracked],
            observation,
            step_index,
            config=ArmConfiguration.of(ArmName.ADAPTIVE_TYPED_RBPF),
            rng=proposal_rng,
            meter=meter,
            relative_probability_coupling_nats=scenario.relative_probability_coupling_nats,
        )
        meter.track_live(len(tracked))
        log_weights = [item.particle.log_weight for item in tracked]
        weights = normalized_weights(log_weights)
        ess = effective_sample_size(weights)
        current = accumulated + _logsumexp(log_weights) - math.log(budget)
        unresolved = _unresolved_probability(current, scenario.observations[: step_index + 1])
        final = step_index == len(scenario.observations) - 1
        decision = threshold_decision(
            ess=ess, particle_count=budget, ess_fraction=policy.ess_fraction, is_final_step=final
        )
        before = _particle_snapshot(tracked, weights)
        for item in tracked:
            chain = item.particle.chain()
            complete_chain_registry.setdefault(chain.key, chain)
        lineage: list[dict[str, str]] = []
        draw: dict[str, object] | None = None
        accumulated_before = accumulated
        if decision["resampling_performed"]:
            indices, draw = resampling_indices(weights, policy.algorithm, resampling_rng)
            accumulated = current
            children: list[TrackedParticle] = []
            for slot, parent_index in enumerate(indices):
                parent = tracked[parent_index]
                child_id = canonical_sha256(
                    {
                        "execution_id": execution_id,
                        "step": step_index,
                        "child_slot": slot,
                        "parent_particle_id": parent.particle_id,
                    }
                )[:24]
                clone = parent.particle.clone()
                clone.log_weight = 0.0
                children.append(
                    TrackedParticle(clone, child_id, parent.particle_id, parent.root_ancestor_id)
                )
                lineage.append(
                    {
                        "child_particle_id": child_id,
                        "parent_particle_id": parent.particle_id,
                        "root_ancestor_id": parent.root_ancestor_id,
                    }
                )
            tracked, after_weights = children, [1.0 / budget] * budget
            meter.resample()
        else:
            after_weights = weights
        after = _particle_snapshot(tracked, after_weights)
        for item in tracked:
            chain = item.particle.chain()
            complete_chain_registry.setdefault(chain.key, chain)
        counters_after = _counter_snapshot(meter)
        steps.append(
            {
                "step_index": step_index,
                "is_final_step": final,
                "ess": ess,
                "threshold": None if policy.ess_fraction is None else policy.ess_fraction * budget,
                "threshold_decision": decision,
                "resampling_algorithm": policy.algorithm,
                "rng_draw": draw,
                "particles_before": before,
                "lineage": lineage,
                "particles_after": after,
                "unknown_support_before": sum(
                    w for p, w in zip(before, weights, strict=True) if p["unknown_support"]
                ),
                "unknown_support_after": sum(
                    w for p, w in zip(after, after_weights, strict=True) if p["unknown_support"]
                ),
                "unresolved_mass_before": unresolved,
                "unresolved_mass_after": unresolved,
                "evidence_ledger": {
                    "accumulated_log_evidence_before": accumulated_before,
                    "current_log_evidence": current,
                    "accumulated_log_evidence_after": accumulated,
                },
                "operation_counter_delta": {
                    key: counters_after[key] - counters_before[key] for key in counters_before
                },
            }
        )
    final_logs = [item.particle.log_weight for item in tracked]
    final_weights = normalized_weights(final_logs)
    final_log_z = accumulated + _logsumexp(final_logs) - math.log(budget)
    unresolved = _unresolved_probability(final_log_z, scenario.observations)
    chain_mass: dict[str, float] = defaultdict(float)
    support_chains: dict[str, Particle] = {}
    for item, weight in zip(tracked, final_weights, strict=True):
        key = item.particle.chain().key
        chain_mass[key] += weight
        support_chains.setdefault(key, item.particle)
    posterior = {key: (1.0 - unresolved) * mass for key, mass in chain_mass.items()}
    posterior[UNRESOLVED_KEY] = unresolved
    meter.ancestry_window_length = max(len(item.particle.ancestry) for item in tracked)
    meter.stop()
    snapshot_table, final_snapshot = _compact_snapshots(steps)
    trace: dict[str, Any] = {
        "schema": TRACE_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "formal_binding_resolved": False,
        "task_12_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "invocation_id": invocation_id,
        "execution_id": execution_id,
        "context": context,
        "split": split,
        "scenario_id": scenario.scenario_id,
        "replicate_seed": replicate_seed,
        "particle_budget": budget,
        "policy": policy.as_dict(),
        "input": _scenario_input(scenario),
        "input_content_sha256": canonical_sha256(_scenario_input(scenario)),
        "rng_schedule": {"proposal": proposal_seed, "resampling": resampling_seed},
        "steps": steps,
        "particle_snapshots": snapshot_table,
        "final_particles": final_snapshot,
        "chain_registry": {
            key: _chain_payload(chain) for key, chain in sorted(complete_chain_registry.items())
        },
        "runtime": {
            "approximate_posterior": dict(sorted(posterior.items())),
            "log_evidence": final_log_z,
            "elementary_evaluations": meter.elementary_likelihood_evaluations,
            "operation_counters": _counter_snapshot(meter),
            "wall_clock_seconds": time.perf_counter() - started,
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "exit_status": 0,
            "exception": None,
            "oracle_access_count": 0,
        },
    }
    trace["deterministic_trace_sha256"] = canonical_sha256(deterministic_trace_projection(trace))
    return trace, support_chains


def attach_evaluator_evidence(
    trace: dict[str, Any],
    support_chains: Mapping[str, Particle],
    scenario: BackboneScenario,
    exact_summary: object,
) -> dict[str, Any]:
    """Attach claims after runtime; raw verification does not consume annotations."""
    exact_posterior = exact_summary.posterior  # type: ignore[attr-defined]
    exact_unresolved = exact_posterior[UNRESOLVED_KEY]
    support_annotations = {
        key: {
            "embodied_action_key": chain_embodied_action(chain.chain(), scenario.observations).key,
            "owner_responsible": (chain.gaps[scenario.corrupt_index].receiver is Actor.OWNER),
        }
        for key, chain in sorted(support_chains.items())
    }
    trace["evaluator"] = {
        "attached_after_runtime": True,
        "truth_chain_sha256": sha256_bytes(scenario.truth.key.encode()),
        "exact_posterior_sha256": _exact_posterior_digest(exact_summary, scenario),
        "exact_log_normalizer": unresolved_log_target(scenario.observations)
        - math.log(exact_unresolved),
        "exact_unresolved_probability": exact_unresolved,
        "exact_embodied_action_posterior": dict(
            sorted(exact_summary.embodied_action_posterior.items())  # type: ignore[attr-defined]
        ),
        "exact_owner_responsibility": exact_summary.owner_responsibility,  # type: ignore[attr-defined]
        "support_annotations": support_annotations,
    }
    trace["deterministic_trace_sha256"] = canonical_sha256(deterministic_trace_projection(trace))
    return trace


def deterministic_trace_projection(trace: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(json.dumps(trace))
    value.pop("deterministic_trace_sha256", None)
    for key in ("wall_clock_seconds", "started_at", "ended_at"):
        value.get("runtime", {}).pop(key, None)
    return value


def runtime_trace_projection(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Projection for the fresh runtime gate; evaluator claims are checked separately."""
    value = deterministic_trace_projection(trace)
    value.pop("evaluator", None)
    return value


def deterministic_result_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    def project(value: object) -> object:
        if isinstance(value, Mapping):
            return {
                str(k): project(v)
                for k, v in value.items()
                if k not in {"wall_clock_seconds", "deterministic_result_sha256"}
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [project(item) for item in value]
        return value

    projected = project(result)
    assert isinstance(projected, dict)
    return projected


def _same_float(value: object, expected: float, tolerance: float = 1e-12) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isclose(float(value), expected, rel_tol=0.0, abs_tol=tolerance)
    )


def verify_raw_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Gate 1: reconstruct from raw particles, weights, chain identity, and ledger."""
    if trace.get("schema") != TRACE_SCHEMA or trace.get("protocol_id") != PROTOCOL_ID:
        raise Task11VerificationError("trace schema/protocol substitution")
    if trace.get("evidence_status") != EVIDENCE_STATUS or trace.get("authority") != AUTHORITY:
        raise Task11VerificationError("trace authority escalation")
    for flag in (
        "formal_binding_resolved",
        "task_12_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if trace.get(flag) is not False:
            raise Task11VerificationError(f"local trace cannot set {flag}")
    policy_data = trace.get("policy")
    if not isinstance(policy_data, Mapping):
        raise Task11VerificationError("missing policy")
    ess_fraction = policy_data.get("ess_fraction")
    if ess_fraction is not None and (
        isinstance(ess_fraction, bool) or not isinstance(ess_fraction, (int, float))
    ):
        raise Task11VerificationError("invalid ESS threshold type")
    policy = Policy(
        str(policy_data.get("algorithm")),
        None if ess_fraction is None else float(ess_fraction),
    )
    if dict(policy_data) != policy.as_dict():
        raise Task11VerificationError("policy semantics mismatch")
    context, scenario_id = str(trace.get("context")), str(trace.get("scenario_id"))
    budget, seed = trace.get("particle_budget"), trace.get("replicate_seed")
    invocation_id = str(trace.get("invocation_id"))
    designs = {
        **GAP_CONTEXTS,
        **(TEST_CONTEXTS if invocation_id.startswith("task11-unit-") else {}),
    }
    if (
        context not in designs
        or not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget <= 0
    ):
        raise Task11VerificationError("invalid context/budget")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise Task11VerificationError("invalid replicate seed")
    expected_id = _execution_id(
        invocation_id,
        context=context,
        scenario_id=scenario_id,
        replicate_seed=seed,
        budget=budget,
        policy_key=policy.key,
    )
    if trace.get("execution_id") != expected_id:
        raise Task11VerificationError("execution identity replay/substitution")
    expected_split = "validation" if seed in VALIDATION_REPLICATE_SEEDS else "confirmatory"
    if trace.get("split") != expected_split:
        raise Task11VerificationError("validation/confirmatory split relabeling")
    scenarios = {item.scenario_id: item for item in registered_scenarios(*designs[context])}
    scenario, input_data = scenarios.get(scenario_id), trace.get("input")
    if scenario is None or input_data != _scenario_input(scenario):
        raise Task11VerificationError("scenario label/content substitution")
    if trace.get("input_content_sha256") != canonical_sha256(input_data):
        raise Task11VerificationError("input content hash mismatch")
    if trace.get("deterministic_trace_sha256") != canonical_sha256(
        deterministic_trace_projection(trace)
    ):
        raise Task11VerificationError("raw trace digest mismatch")
    runtime, steps = trace.get("runtime"), trace.get("steps")
    final_particles = _resolve_snapshot(trace, trace.get("final_particles"))
    registry_data = trace.get("chain_registry")
    if not isinstance(runtime, Mapping) or not isinstance(steps, list) or not steps:
        raise Task11VerificationError("runtime/step evidence missing")
    if runtime.get("exit_status") != 0 or runtime.get("exception") is not None:
        raise Task11VerificationError("failed trace cannot be treated as successful")
    if runtime.get("oracle_access_count") != 0:
        raise Task11VerificationError("oracle leaked into deployable runtime")
    if len(final_particles) != budget:
        raise Task11VerificationError("final particle matrix incomplete")
    if not isinstance(registry_data, Mapping):
        raise Task11VerificationError("chain registry missing")
    chains: dict[str, ChainHypothesis] = {}
    for key, payload in registry_data.items():
        if not isinstance(payload, Mapping):
            raise Task11VerificationError("malformed chain registry")
        chain = _chain_from_payload(payload)
        if chain.key != key:
            raise Task11VerificationError("chain identity/payload mismatch")
        chains[str(key)] = chain

    def validate_chain_annotations(rows: Sequence[Mapping[str, Any]]) -> None:
        for item in rows:
            chain = chains.get(str(item.get("chain_key")))
            if chain is None:
                raise Task11VerificationError("snapshot chain identity missing from registry")
            if item.get("unknown_support") is not _chain_has_unknown(chain):
                raise Task11VerificationError(
                    "unknown support annotation not derived from chain identity"
                )

    accumulated, elementary, trigger_count = 0.0, 0, 0
    events: list[int] = []
    ess_trajectory: list[float] = []
    prior_after: list[Mapping[str, Any]] | None = None
    expected_rng = random.Random(
        f"{PROTOCOL_ID}:resampling:{context}:{scenario_id}:{budget}:{seed}:{policy.key}"
    )
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping) or step.get("step_index") != index:
            raise Task11VerificationError("step order mismatch")
        before = _resolve_snapshot(trace, step.get("particles_before"))
        after = _resolve_snapshot(trace, step.get("particles_after"))
        lineage, ledger = step.get("lineage"), step.get("evidence_ledger")
        if len(before) != budget or len(after) != budget:
            raise Task11VerificationError("particle snapshot incomplete")
        validate_chain_annotations(before)
        validate_chain_annotations(after)
        if not isinstance(lineage, list) or not isinstance(ledger, Mapping):
            raise Task11VerificationError("lineage/evidence ledger missing")
        if prior_after is not None:

            def identity(
                rows: Sequence[Mapping[str, Any]],
            ) -> list[tuple[object, object, object]]:
                return [
                    (item["particle_id"], item["parent_particle_id"], item["root_ancestor_id"])
                    for item in rows
                ]

            if identity(before) != identity(prior_after):
                raise Task11VerificationError("particle identity/root chain discontinuity")
        logs = [float(item["log_weight"]) for item in before]
        weights = normalized_weights(logs)
        for item, weight in zip(before, weights, strict=True):
            if not _same_float(item.get("normalized_weight"), weight):
                raise Task11VerificationError("normalized weight not derived from raw log weight")
        ess = effective_sample_size(weights)
        if not _same_float(step.get("ess"), ess):
            raise Task11VerificationError("ESS not derived from raw weights")
        ess_trajectory.append(ess)
        final = index == len(steps) - 1
        decision = threshold_decision(
            ess=ess, particle_count=budget, ess_fraction=policy.ess_fraction, is_final_step=final
        )
        if step.get("threshold_decision") != decision or step.get("is_final_step") is not final:
            raise Task11VerificationError("threshold/final-step decision mismatch")
        threshold = None if policy.ess_fraction is None else policy.ess_fraction * budget
        if step.get("threshold") != threshold:
            raise Task11VerificationError("threshold drift")
        if decision["below_threshold"] and not final:
            trigger_count += 1
        current = accumulated + _logsumexp(logs) - math.log(budget)
        unresolved = _unresolved_probability(current, scenario.observations[: index + 1])
        if not _same_float(
            step.get("unresolved_mass_before"), unresolved, 1e-14
        ) or not _same_float(step.get("unresolved_mass_after"), unresolved, 1e-14):
            raise Task11VerificationError(
                "unresolved mass not recomputed from observations and ledger"
            )
        if not _same_float(
            ledger.get("accumulated_log_evidence_before"), accumulated
        ) or not _same_float(ledger.get("current_log_evidence"), current):
            raise Task11VerificationError("cumulative evidence ledger mismatch")
        unknown_before = sum(
            weight
            for item, weight in zip(before, weights, strict=True)
            if item.get("unknown_support") is True
        )
        if not _same_float(step.get("unknown_support_before"), unknown_before):
            raise Task11VerificationError("unknown support before mismatch")
        if decision["resampling_performed"]:
            events.append(index)
            indices, draw = resampling_indices(weights, policy.algorithm, expected_rng)
            if step.get("rng_draw") != draw or len(lineage) != budget:
                raise Task11VerificationError("resampling RNG/lineage mismatch")
            before_ids = {item["particle_id"] for item in before}
            for slot, (entry, child, parent_index) in enumerate(
                zip(lineage, after, indices, strict=True)
            ):
                parent = before[parent_index]
                child_id = canonical_sha256(
                    {
                        "execution_id": expected_id,
                        "step": index,
                        "child_slot": slot,
                        "parent_particle_id": parent["particle_id"],
                    }
                )[:24]
                if (
                    parent["particle_id"] not in before_ids
                    or entry.get("child_particle_id") != child_id
                    or child.get("particle_id") != child_id
                    or entry.get("parent_particle_id") != parent["particle_id"]
                    or child.get("parent_particle_id") != parent["particle_id"]
                    or entry.get("root_ancestor_id") != parent["root_ancestor_id"]
                    or child.get("root_ancestor_id") != parent["root_ancestor_id"]
                    or child.get("chain_key") != parent["chain_key"]
                    or float(child.get("log_weight", math.nan)) != 0.0
                ):
                    raise Task11VerificationError("parent/root ancestry mismatch")
            accumulated = current
        elif lineage or step.get("rng_draw") is not None or after != before:
            raise Task11VerificationError("zero-event arm contains fabricated change")
        if not _same_float(ledger.get("accumulated_log_evidence_after"), accumulated):
            raise Task11VerificationError("post-event evidence ledger mismatch")
        after_logs = [float(item["log_weight"]) for item in after]
        after_weights = normalized_weights(after_logs)
        for item, weight in zip(after, after_weights, strict=True):
            if not _same_float(item.get("normalized_weight"), weight):
                raise Task11VerificationError(
                    "post-decision normalized weight not derived from raw log weight"
                )
        unknown_after = sum(
            weight
            for item, weight in zip(after, after_weights, strict=True)
            if item.get("unknown_support") is True
        )
        if not _same_float(step.get("unknown_support_after"), unknown_after):
            raise Task11VerificationError("unknown support after mismatch")
        delta = step.get("operation_counter_delta")
        if not isinstance(delta, Mapping) or any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in delta.values()
        ):
            raise Task11VerificationError("invalid operation counter ledger")
        elementary += int(delta.get("elementary_likelihood_evaluations", 0))
        prior_after = after
    if final_particles != prior_after:
        raise Task11VerificationError("final particles differ from final step")
    final_logs = [float(item["log_weight"]) for item in final_particles]
    final_weights = normalized_weights(final_logs)
    for item, weight in zip(final_particles, final_weights, strict=True):
        if not _same_float(item.get("normalized_weight"), weight):
            raise Task11VerificationError("final normalized weights mismatch")
        if item.get("chain_key") not in chains:
            raise Task11VerificationError("final chain identity missing from registry")
    final_log_z = accumulated + _logsumexp(final_logs) - math.log(budget)
    unresolved = _unresolved_probability(final_log_z, scenario.observations)
    chain_mass: dict[str, float] = defaultdict(float)
    for item, weight in zip(final_particles, final_weights, strict=True):
        chain_mass[str(item["chain_key"])] += weight
    posterior = {key: (1.0 - unresolved) * mass for key, mass in chain_mass.items()}
    posterior[UNRESOLVED_KEY] = unresolved
    claimed = runtime.get("approximate_posterior")
    if (
        not isinstance(claimed, Mapping)
        or set(claimed) != set(posterior)
        or any(not _same_float(claimed[key], value, 1e-14) for key, value in posterior.items())
    ):
        raise Task11VerificationError(
            "runtime approximate posterior differs from raw recomputation"
        )
    if not _same_float(runtime.get("log_evidence"), final_log_z):
        raise Task11VerificationError("runtime log normalizer differs from raw recomputation")
    counters = runtime.get("operation_counters")
    if (
        not isinstance(counters, Mapping)
        or counters.get("elementary_likelihood_evaluations") != elementary
        or counters.get("resampling_events") != len(events)
        or runtime.get("elementary_evaluations") != elementary
    ):
        raise Task11VerificationError("operation counter summary mismatch")
    approximate_actions: dict[str, float] = defaultdict(float)
    approximate_owner = 0.0
    for key, probability in posterior.items():
        if key == UNRESOLVED_KEY:
            continue
        chain = chains[key]
        approximate_actions[chain_embodied_action(chain, scenario.observations).key] += probability
        if chain.gaps[scenario.corrupt_index].receiver is Actor.OWNER:
            approximate_owner += probability
    resolved = sum(approximate_actions.values())
    actions = (
        {key: value / resolved for key, value in approximate_actions.items()} if resolved else {}
    )
    event_count = len(events)
    policy_gate = (
        event_count == 0 if policy.algorithm == "no_resampling" else event_count == trigger_count
    )
    expectation = (
        "no_resampling_requires_zero_events_and_zero_lineage"
        if policy.algorithm == "no_resampling"
        else "threshold_not_triggered_requires_zero_events_and_zero_lineage"
        if trigger_count == 0
        else "each_nonfinal_threshold_trigger_requires_one_event_with_parent_root_lineage"
    )
    wall = runtime.get("wall_clock_seconds")
    if (
        isinstance(wall, bool)
        or not isinstance(wall, (int, float))
        or not math.isfinite(wall)
        or wall < 0
    ):
        raise Task11VerificationError("invalid wall clock")
    return {
        "execution_id": expected_id,
        "invocation_id": invocation_id,
        "context": context,
        "split": trace["split"],
        "scenario_id": scenario_id,
        "replicate_seed": seed,
        "particle_budget": budget,
        "policy": policy.as_dict(),
        "approximate_posterior": dict(sorted(posterior.items())),
        "approximate_action_posterior": dict(sorted(actions.items())),
        "approximate_owner_responsibility": approximate_owner,
        "approximate_log_normalizer": final_log_z,
        "ess_trajectory": ess_trajectory,
        "resampling_event_indices": events,
        "trigger_count": trigger_count,
        "event_count": event_count,
        "runtime_policy_trace_expectation": expectation,
        "unique_parent_count": (
            len({entry["parent_particle_id"] for step in steps for entry in step["lineage"]})
            if events
            else budget
        ),
        "unique_root_ancestor_count": len({item["root_ancestor_id"] for item in final_particles}),
        "unknown_support_before": float(steps[0]["unknown_support_before"]),
        "unknown_support_after": float(steps[-1]["unknown_support_after"]),
        "unresolved_mass_before": float(steps[0]["unresolved_mass_before"]),
        "unresolved_mass_after": unresolved,
        "elementary_evaluations": elementary,
        "wall_clock_seconds": float(wall),
        "gates": {
            "raw_only_recomputation": True,
            "finite_normalized_weights": True,
            "lineage_parent_root_recorded": True,
            "final_step_not_resampled": len(steps) - 1 not in events,
            "unknown_unresolved_support_recomputed": True,
            "runtime_policy_trace_changes": policy_gate,
            "no_oracle_access": True,
        },
    }


verify_and_recompute_trace = verify_raw_trace


def _exact_summary(scenario: BackboneScenario) -> object:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    meter.start()
    result = exact_decision_summary(
        scenario, meter, caller_role=CallerRole.EXACT_ORACLE, state_budget=2_000_000
    )
    meter.stop()
    return result


def _exact_posterior_digest(exact: object, scenario: BackboneScenario) -> str:
    identity = canonical_sha256(_scenario_input(scenario))
    digest = _EXACT_POSTERIOR_DIGEST_CACHE.get(identity)
    if digest is None:
        digest = canonical_sha256(exact.posterior)  # type: ignore[attr-defined]
        _EXACT_POSTERIOR_DIGEST_CACHE[identity] = digest
    return digest


def _add_exact_metrics(
    raw: dict[str, Any], trace: Mapping[str, Any], scenario: BackboneScenario, exact: object
) -> dict[str, Any]:
    evaluator = trace.get("evaluator")
    exact_posterior = exact.posterior  # type: ignore[attr-defined]
    exact_unresolved = exact_posterior[UNRESOLVED_KEY]
    exact_log_z = unresolved_log_target(scenario.observations) - math.log(exact_unresolved)
    exact_actions = dict(sorted(exact.embodied_action_posterior.items()))  # type: ignore[attr-defined]
    exact_owner = exact.owner_responsibility  # type: ignore[attr-defined]
    chain_registry = trace.get("chain_registry")
    if not isinstance(chain_registry, Mapping):
        raise Task11VerificationError("chain registry missing from trace")
    approximate = raw["approximate_posterior"]
    support_keys = set(approximate) - {UNRESOLVED_KEY}
    if not support_keys <= set(chain_registry):
        raise Task11VerificationError("final approximate support missing from chain registry")
    support_annotations = {
        str(key): {
            "embodied_action_key": chain_embodied_action(
                _chain_from_payload(payload), scenario.observations
            ).key,
            "owner_responsible": (
                _chain_from_payload(payload).gaps[scenario.corrupt_index].receiver is Actor.OWNER
            ),
        }
        for key, payload in sorted(chain_registry.items())
        if key in support_keys and isinstance(payload, Mapping)
    }
    expected = {
        "attached_after_runtime": True,
        "truth_chain_sha256": sha256_bytes(scenario.truth.key.encode()),
        "exact_posterior_sha256": _exact_posterior_digest(exact, scenario),
        "exact_log_normalizer": exact_log_z,
        "exact_unresolved_probability": exact_unresolved,
        "exact_embodied_action_posterior": exact_actions,
        "exact_owner_responsibility": exact_owner,
        "support_annotations": support_annotations,
    }
    if not isinstance(evaluator, Mapping) or dict(evaluator) != expected:
        raise Task11VerificationError("evaluator claims differ from fresh exact recomputation")
    exact_mass_on_support = sum(exact_posterior.get(key, 0.0) for key in support_keys)
    exact_other = max(0.0, 1.0 - exact_unresolved - exact_mass_on_support)
    posterior_tv = 0.5 * (
        sum(abs(approximate[key] - exact_posterior.get(key, 0.0)) for key in support_keys)
        + abs(approximate[UNRESOLVED_KEY] - exact_unresolved)
        + exact_other
    )
    action_distance = action_posterior_distance(exact_actions, raw["approximate_action_posterior"])
    raw.update(
        {
            "action_loss": action_distance,
            "posterior_total_variation": posterior_tv,
            "action_posterior_distance": action_distance,
            "owner_contamination": abs(raw["approximate_owner_responsibility"] - exact_owner),
            "log_normalizer_bias": raw["approximate_log_normalizer"] - exact_log_z,
        }
    )
    raw["gates"]["fresh_exact_recomputation"] = True
    return raw


def verify_trace_against_fresh_execution(
    trace: Mapping[str, Any], *, exact_summary_cache: object | None = None
) -> dict[str, Any]:
    """Gate 2: current-source replay, independent of the raw-only gate."""
    raw = verify_raw_trace(trace)
    designs = {**GAP_CONTEXTS, **TEST_CONTEXTS}
    scenario = next(
        item
        for item in registered_scenarios(*designs[raw["context"]])
        if item.scenario_id == raw["scenario_id"]
    )
    policy_data = raw["policy"]
    fresh, chains = run_approximate_trace(
        scenario,
        context=raw["context"],
        replicate_seed=raw["replicate_seed"],
        budget=raw["particle_budget"],
        policy=Policy(policy_data["algorithm"], policy_data["ess_fraction"]),
        invocation_id=raw["invocation_id"],
    )
    exact = exact_summary_cache or _exact_summary(scenario)
    attach_evaluator_evidence(fresh, chains, scenario, exact)
    if canonical_sha256(runtime_trace_projection(trace)) != canonical_sha256(
        runtime_trace_projection(fresh)
    ):
        raise Task11VerificationError("fresh source-bound trace replay mismatch")
    raw["gates"]["fresh_source_replay"] = True
    return _add_exact_metrics(raw, trace, scenario, exact)


def expected_trace_count() -> int:
    return sum(
        len(registered_scenarios(*GAP_CONTEXTS[context]))
        * len(ALL_REPLICATE_SEEDS)
        * len(POLICIES)
        * len(CONTEXT_BUDGETS[context])
        for context in GAP_CONTEXTS
    )


def expected_condition_count() -> int:
    return sum(len(CONTEXT_BUDGETS[context]) * len(POLICIES) for context in GAP_CONTEXTS)


def expected_coordinates() -> set[tuple[str, str, int, int, str]]:
    return {
        (context, scenario.scenario_id, seed, budget, policy.key)
        for context in GAP_CONTEXTS
        for scenario in registered_scenarios(*GAP_CONTEXTS[context])
        for seed in ALL_REPLICATE_SEEDS
        for budget in CONTEXT_BUDGETS[context]
        for policy in POLICIES
    }


def validate_trace_matrix(traces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [verify_raw_trace(trace) for trace in traces]
    if len({row["invocation_id"] for row in rows}) != 1:
        raise Task11VerificationError("whole matrix must use one unique invocation ID")
    coordinates = {
        (
            row["context"],
            row["scenario_id"],
            row["replicate_seed"],
            row["particle_budget"],
            row["policy"]["key"],
        )
        for row in rows
    }
    if len(coordinates) != len(rows) or coordinates != expected_coordinates():
        raise Task11VerificationError(
            "trace matrix has missing, duplicate, extra, or replayed rows"
        )
    rows.sort(
        key=lambda row: (
            row["context"],
            row["particle_budget"],
            row["scenario_id"],
            row["replicate_seed"],
            row["policy"]["key"],
        )
    )
    return rows


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        raise Task11VerificationError("cannot average empty rows")
    return sum(items) / len(items)


def _aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    fields = (
        "paired_action_loss_delta_per_elementary_evaluation",
        "posterior_total_variation",
        "action_posterior_distance",
        "owner_contamination",
        "log_normalizer_bias",
        "elementary_evaluations",
        "wall_clock_seconds",
        "unique_parent_count",
        "unique_root_ancestor_count",
        "unknown_support_before",
        "unknown_support_after",
        "unresolved_mass_before",
        "unresolved_mass_after",
        "trigger_count",
        "event_count",
    )
    return {field: _mean(float(row[field]) for row in rows) for field in fields}


def _eligible(metrics: Mapping[str, float]) -> bool:
    return (
        metrics["posterior_total_variation"] <= 0.05
        and metrics["owner_contamination"] <= 0.05
        and abs(metrics["log_normalizer_bias"]) <= 0.05
    )


def toy_distribution_frequency_gate(*, draws: int = 20_000) -> bool:
    weights = [0.05, 0.15, 0.30, 0.50]
    for algorithm in ALGORITHMS[1:]:
        counts = [0] * len(weights)
        rng = random.Random(f"{PROTOCOL_ID}:toy:{algorithm}")
        for _ in range(draws // len(weights)):
            for index in resampling_indices(weights, algorithm, rng)[0]:
                counts[index] += 1
        observed = [count / sum(counts) for count in counts]
        if any(abs(a - b) > 0.015 for a, b in zip(observed, weights, strict=True)):
            return False
    return True


def recompute_results(
    traces: Iterable[Mapping[str, Any]], *, fresh_replay: bool = True
) -> dict[str, Any]:
    """Derive the full result; caller cannot disable the fresh-source gate."""
    if not fresh_replay:
        raise Task11VerificationError("complete result requires fresh-source replay")
    rows: list[dict[str, Any]] = []
    coordinates: set[tuple[str, str, int, int, str]] = set()
    invocations: set[str] = set()
    exact_scenario_id: str | None = None
    exact: object | None = None
    for trace in traces:
        raw = verify_raw_trace(trace)
        coordinate = (
            raw["context"],
            raw["scenario_id"],
            raw["replicate_seed"],
            raw["particle_budget"],
            raw["policy"]["key"],
        )
        if coordinate in coordinates:
            raise Task11VerificationError("duplicate or replayed trace coordinate")
        coordinates.add(coordinate)
        invocations.add(raw["invocation_id"])
        if raw["scenario_id"] != exact_scenario_id:
            scenario = next(
                item
                for item in registered_scenarios(*GAP_CONTEXTS[raw["context"]])
                if item.scenario_id == raw["scenario_id"]
            )
            exact = _exact_summary(scenario)
            exact_scenario_id = raw["scenario_id"]
        assert exact is not None
        rows.append(
            verify_trace_against_fresh_execution(
                trace,
                exact_summary_cache=exact,
            )
        )
    if len(invocations) != 1:
        raise Task11VerificationError("whole matrix must use one unique invocation ID")
    if coordinates != expected_coordinates():
        raise Task11VerificationError("trace matrix has missing, extra, or replayed rows")
    rows.sort(
        key=lambda row: (
            row["context"],
            row["particle_budget"],
            row["scenario_id"],
            row["replicate_seed"],
            row["policy"]["key"],
        )
    )
    by_unit = {
        (
            row["context"],
            row["scenario_id"],
            row["replicate_seed"],
            row["particle_budget"],
            row["policy"]["key"],
        ): row
        for row in rows
    }
    for row in rows:
        baseline = by_unit[
            (
                row["context"],
                row["scenario_id"],
                row["replicate_seed"],
                row["particle_budget"],
                "no_resampling",
            )
        ]
        row["paired_action_loss_delta_per_elementary_evaluation"] = (
            row["action_loss"] - baseline["action_loss"]
        ) / row["elementary_evaluations"]
    conditions: list[dict[str, Any]] = []
    contexts: dict[str, Any] = {}
    toy_gate = toy_distribution_frequency_gate()
    for context in GAP_CONTEXTS:
        budget_payload: dict[str, Any] = {}
        for budget in CONTEXT_BUDGETS[context]:
            budget_conditions: list[dict[str, Any]] = []
            for policy in POLICIES:
                group = [
                    row
                    for row in rows
                    if row["context"] == context
                    and row["particle_budget"] == budget
                    and row["policy"]["key"] == policy.key
                ]
                validation = [row for row in group if row["split"] == "validation"]
                confirmatory = [row for row in group if row["split"] == "confirmatory"]
                gates = {
                    "raw_only_recomputation": all(
                        row["gates"]["raw_only_recomputation"] for row in group
                    ),
                    "fresh_source_replay": all(
                        row["gates"]["fresh_source_replay"] for row in group
                    ),
                    "fresh_exact_recomputation": all(
                        row["gates"]["fresh_exact_recomputation"] for row in group
                    ),
                    "finite_normalized_weights": all(
                        row["gates"]["finite_normalized_weights"] for row in group
                    ),
                    "toy_distribution_frequency": toy_gate,
                    "lineage_parent_root_recorded": all(
                        row["gates"]["lineage_parent_root_recorded"] for row in group
                    ),
                    "final_step_not_resampled": all(
                        row["gates"]["final_step_not_resampled"] for row in group
                    ),
                    "unknown_unresolved_support_recomputed": all(
                        row["gates"]["unknown_unresolved_support_recomputed"] for row in group
                    ),
                    "runtime_policy_trace_changes": all(
                        row["gates"]["runtime_policy_trace_changes"] for row in group
                    ),
                    "no_oracle_access": all(row["gates"]["no_oracle_access"] for row in group),
                }
                condition = {
                    "context": context,
                    "particle_budget": budget,
                    "policy": policy.as_dict(),
                    "row_count": len(group),
                    "validation_row_count": len(validation),
                    "confirmatory_row_count": len(confirmatory),
                    "validation": _aggregate_rows(validation),
                    "confirmatory": _aggregate_rows(confirmatory),
                    "all_rows": _aggregate_rows(group),
                    "runtime_policy_trace_expectations": sorted(
                        {row["runtime_policy_trace_expectation"] for row in group}
                    ),
                    "gates": gates,
                    "all_correctness_gates_passed": all(gates.values()),
                }
                conditions.append(condition)
                budget_conditions.append(condition)
            selected: dict[str, str | None] = {}
            for algorithm in ALGORITHMS[1:]:
                candidates = [
                    item
                    for item in budget_conditions
                    if item["policy"]["algorithm"] == algorithm
                    and item["all_correctness_gates_passed"]
                    and _eligible(item["validation"])
                ]
                candidates.sort(
                    key=lambda item: (
                        item["validation"]["paired_action_loss_delta_per_elementary_evaluation"],
                        item["policy"]["key"],
                    )
                )
                selected[algorithm] = candidates[0]["policy"]["key"] if candidates else None
            deployable_keys = {"no_resampling"} | {
                key
                for algorithm, key in selected.items()
                if algorithm != NEGATIVE_CONTROL and key is not None
            }
            all_gates = all(item["all_correctness_gates_passed"] for item in budget_conditions)
            deployable = (
                [
                    item
                    for item in budget_conditions
                    if item["policy"]["key"] in deployable_keys and _eligible(item["confirmatory"])
                ]
                if all_gates
                else []
            )
            deployable.sort(
                key=lambda item: (
                    item["confirmatory"]["paired_action_loss_delta_per_elementary_evaluation"],
                    item["policy"]["key"],
                )
            )
            candidate = deployable[0]["policy"] if deployable else None
            budget_payload[str(budget)] = {
                "validation_selected_thresholds": selected,
                "local_diagnostic_candidate": candidate,
                "disposition": (
                    "RAN_INELIGIBLE_CORRECTNESS_GATE_FAILURE"
                    if not all_gates
                    else "RAN_ELIGIBLE_SELECTION"
                    if candidate
                    else "RAN_ELIGIBLE_NO_SELECTION"
                ),
                "all_correctness_gates_passed": all_gates,
                "formal_binding_resolved": False,
            }
        contexts[context] = {
            "budgets": budget_payload,
            "budget_dependent": len(
                {
                    canonical_sha256(payload["local_diagnostic_candidate"])
                    for payload in budget_payload.values()
                }
            )
            > 1,
            "formal_budget_selected": None,
            "formal_binding_resolved": False,
        }
    shared = sorted(set(CONTEXT_BUDGETS["G1"]) & set(CONTEXT_BUDGETS["G2"]))
    result: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "formal_binding_resolved": False,
        "task_12_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "invocation_id": rows[0]["invocation_id"],
        "context_budgets": {key: list(value) for key, value in CONTEXT_BUDGETS.items()},
        "particle_budget_is_formally_selected": False,
        "formal_particle_budget": None,
        "validation_replicate_seeds": list(VALIDATION_REPLICATE_SEEDS),
        "confirmatory_replicate_seeds": list(CONFIRMATORY_REPLICATE_SEEDS),
        "condition_count": len(conditions),
        "trace_count": len(rows),
        "zero_event_trace_count": sum(row["event_count"] == 0 for row in rows),
        "multi_event_trace_count": sum(row["event_count"] >= 2 for row in rows),
        "conditions": conditions,
        "contexts": contexts,
        "budget_dependent_results": {
            context: contexts[context]["budget_dependent"] for context in contexts
        },
        "context_dependent_results": any(
            contexts["G1"]["budgets"][str(budget)]["local_diagnostic_candidate"]
            != contexts["G2"]["budgets"][str(budget)]["local_diagnostic_candidate"]
            for budget in shared
        ),
        "raw_only_verification_gate": True,
        "fresh_source_replay_gate": True,
        "claim_boundary": (
            "Complete frozen-budget local diagnostic, not complete/formal Task 11. "
            "No Task 10 resolution receipt or independent custody exists; no formal budget is selected."
        ),
    }
    result["deterministic_result_sha256"] = canonical_sha256(
        deterministic_result_projection(result)
    )
    return result


def verify_recomputed_result(
    reported: Mapping[str, Any], traces: Iterable[Mapping[str, Any]], *, fresh_replay: bool = True
) -> dict[str, Any]:
    recomputed = recompute_results(traces, fresh_replay=fresh_replay)
    if reported != recomputed:
        raise Task11VerificationError("reported result differs from raw/fresh recomputation")
    return recomputed


def render_diagnostic_report(
    summary: Mapping[str, Any], raw_hashes: Mapping[str, str], source_commit: str
) -> str:
    """Render the one canonical result report that the manifest accepts."""
    lines = [
        "# Structure Two Task 11 full-budget resampling diagnostic",
        "",
        "Date: 2026-09-06",
        f"Evidence status: `{EVIDENCE_STATUS}` / `{AUTHORITY}`",
        f"Producer source commit: `{source_commit}`",
        "",
        "## Outcome",
        "",
        "This is the complete frozen-budget local diagnostic matrix. It is not complete/formal "
        "Task 11. The earlier K=24-only run is retained separately as a historical local pilot. "
        "The pre-audit full-budget package is superseded by this adversarial rerun.",
        "",
        "```text",
        "formal_binding_resolved=false",
        "task_12_unlocked=false",
        "seven_operator_ablation_authorized=false",
        "```",
        "",
        "No formal particle budget was selected.",
        "",
        "## Budget- and context-dependent results",
        "",
    ]
    contexts = summary["contexts"]
    for context in ("G1", "G2"):
        lines.extend(
            [f"### {context}", "", "| Budget | Candidate | Disposition |", "|---:|---|---|"]
        )
        for budget in CONTEXT_BUDGETS[context]:
            payload = contexts[context]["budgets"][str(budget)]
            lines.append(
                f"| {budget} | `{json.dumps(payload['local_diagnostic_candidate'], sort_keys=True)}` | `{payload['disposition']}` |"
            )
        lines.extend(
            ["", f"`budget_dependent={str(contexts[context]['budget_dependent']).lower()}`", ""]
        )
    lines.extend(
        [
            f"Across shared budgets, `context_dependent_results={str(summary['context_dependent_results']).lower()}`.",
            "",
            "## Evidence",
            "",
            f"- Conditions: `{summary['condition_count']}`.",
            f"- Raw traces: `{summary['trace_count']}`.",
            f"- Zero-event raw traces: `{summary['zero_event_trace_count']}`.",
            f"- Multi-event raw traces: `{summary['multi_event_trace_count']}`.",
            f"- G1 raw SHA-256: `{raw_hashes['G1']}`.",
            f"- G2 raw SHA-256: `{raw_hashes['G2']}`.",
            "- Raw-only recomputation and fresh-source replay are separate required gates.",
            "- Approximate posterior, unresolved mass, log normalizer, action posterior, owner mass, "
            "post-resampling weights, and unknown-support flags are reconstructed without trusting "
            "runtime posterior or evaluator annotations.",
            "",
            "## Unclosed formal trust dependencies",
            "",
            "No independently enrolled Task 10 resolution receipt, external timestamp authority, "
            "independent artifact custody, or independent execution witness exists. Local commit and "
            "hash consistency therefore cannot establish historical authenticity or formal state "
            "transition.",
            "",
        ]
    )
    return "\n".join(lines)


def run_context_matrix(*, context: str, invocation_id: str) -> Iterator[dict[str, Any]]:
    for scenario in registered_scenarios(*GAP_CONTEXTS[context]):
        exact = _exact_summary(scenario)
        for budget in CONTEXT_BUDGETS[context]:
            for seed in ALL_REPLICATE_SEEDS:
                for policy in POLICIES:
                    trace, chains = run_approximate_trace(
                        scenario,
                        context=context,
                        replicate_seed=seed,
                        budget=budget,
                        policy=policy,
                        invocation_id=invocation_id,
                    )
                    yield attach_evaluator_evidence(trace, chains, scenario, exact)


def run_complete_matrix(*, invocation_id: str) -> Iterator[dict[str, Any]]:
    for context in GAP_CONTEXTS:
        yield from run_context_matrix(context=context, invocation_id=invocation_id)


def verify_formal_task11_path(*, task_10_resolution_receipt: object | None = None) -> None:
    _ = task_10_resolution_receipt
    raise FormalTask11UnavailableError(
        "formal Task 11 unavailable: trust anchor is NOT_ENROLLED and local evidence lacks custody"
    )


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    raw = path.open("rb")
    stream = gzip.GzipFile(fileobj=raw, mode="rb") if path.suffix == ".gz" else raw
    try:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise Task11VerificationError(f"JSONL row {line_number} is not an object")
            yield value
    finally:
        stream.close()
        if stream is not raw:
            raw.close()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw:
        stream = (
            gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0)
            if path.suffix == ".gz"
            else raw
        )
        try:
            for row in rows:
                stream.write(canonical_json_bytes(row) + b"\n")
        finally:
            if stream is not raw:
                stream.close()
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, path)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def dependency_snapshot(root: Path) -> dict[str, object]:
    packages = sorted(
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in distributions()
        if distribution.metadata["Name"]
    )
    return {
        "python": sys.version,
        "python_executable_name": Path(sys.executable).name,
        "os": platform.platform(),
        "machine": platform.machine(),
        "dependency_lock": packages,
    }


def _source_inventory(root: Path) -> dict[str, Any]:
    """Hash the exact current local sources used by this unauthenticated run.

    A Git commit is intentionally not treated as a trust anchor here: a dirty
    worktree can still produce a reproducible local diagnostic when every
    executable source is content-bound, but it cannot claim historical
    authenticity or independent custody.
    """

    paths = set(SOURCE_RELATIVE_PATHS) | set(COMPONENT_INVENTORY.values())
    resolved_root = root.resolve()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.suffix == ".py" and path.is_relative_to(resolved_root):
            relative = path.relative_to(resolved_root).as_posix()
            if relative.startswith(("src/", "apps/")):
                paths.add(relative)
    inventory: dict[str, Any] = {}
    for relative in sorted(paths):
        current = _read_regular_file(root / relative)
        inventory[relative] = {"sha256": sha256_bytes(current)}
    return inventory


def _verify_exact_command(command: Sequence[str]) -> None:
    expected_prefix = (
        "apps/evaluation_runner/run_structure_two_task11_resampling_diagnostic.py",
        "--output-dir",
        OUTPUT_RELATIVE,
        "--invocation-id",
        FINAL_INVOCATION_ID,
    )
    accepted = {
        expected_prefix,
        (*expected_prefix, "--recover-raw-dir", RECOVERY_RAW_RELATIVE),
    }
    if (
        not command
        or Path(command[0]).name not in {"python", "python3"}
        or tuple(command[1:]) not in accepted
    ):
        raise Task11VerificationError("unexpected or malicious execution command")


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise Task11VerificationError(f"{label} timestamp missing")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise Task11VerificationError(f"{label} timestamp lacks timezone")
    return parsed.astimezone(UTC)


def _stdout_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _read_regular_file(path).decode().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    return fields


def build_evidence_manifest(
    *,
    repository_root: Path,
    output_dir: Path,
    exact_command: Sequence[str],
    producer_source_commit: str,
    start_timestamp: str,
    end_timestamp: str,
    stdout_path: Path,
    stderr_path: Path,
    preflight_working_tree_status: Sequence[str],
) -> dict[str, Any]:
    _verify_exact_command(exact_command)
    if _git(repository_root, "rev-parse", "HEAD") != producer_source_commit:
        raise Task11VerificationError("experiment did not run at producer source commit")
    inventory = _source_inventory(repository_root)
    status = working_tree_status(repository_root)
    artifacts = {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "TASK11_EVIDENCE_MANIFEST.json" and not path.is_symlink()
    }
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "evidence_status": EVIDENCE_STATUS,
        "authority": AUTHORITY,
        "formal_binding_resolved": False,
        "task_12_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "base_commit": BASE_COMMIT,
        "producer_source_commit": producer_source_commit,
        "component_inventory": COMPONENT_INVENTORY,
        "source_inventory": inventory,
        "source_bundle_sha256": canonical_sha256(inventory),
        "frozen_input_hashes": verify_frozen_inputs(repository_root),
        "dataset_seed_split_hash": canonical_sha256(
            {
                "contexts": GAP_CONTEXTS,
                "budgets": CONTEXT_BUDGETS,
                "validation": VALIDATION_REPLICATE_SEEDS,
                "confirmatory": CONFIRMATORY_REPLICATE_SEEDS,
            }
        ),
        "environment": dependency_snapshot(repository_root),
        "execution_command": list(exact_command),
        "invocation_id": FINAL_INVOCATION_ID,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "generated_at": utc_now(),
        "execution_exit_status": 0,
        "preflight_working_tree_clean": not preflight_working_tree_status,
        "preflight_working_tree_status": list(preflight_working_tree_status),
        "postrun_working_tree_drift": status,
        "postrun_drift_only_output_artifacts": False,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "artifact_hashes": artifacts,
        "claim_boundary": (
            "Current-source hashes establish local internal consistency only. The Git HEAD is "
            "context, not a claim that the worktree was clean or committed; neither historical "
            "authenticity nor independent custody is established, so formal Task 11 is unresolved."
        ),
    }
    manifest["content_sha256"] = canonical_sha256(manifest)
    return manifest


def verify_evidence_manifest(
    manifest: Mapping[str, Any],
    *,
    repository_root: Path,
    output_dir: Path,
) -> None:
    unsigned = dict(manifest)
    stored = unsigned.pop("content_sha256", None)
    if stored != canonical_sha256(unsigned):
        raise Task11VerificationError("manifest self-hash mismatch")
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("evidence_status") != EVIDENCE_STATUS
        or manifest.get("authority") != AUTHORITY
    ):
        raise Task11VerificationError("manifest schema/authority escalation")
    for flag in (
        "formal_binding_resolved",
        "task_12_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if manifest.get(flag) is not False:
            raise Task11VerificationError(f"manifest cannot set {flag}")
    producer = manifest.get("producer_source_commit")
    if not isinstance(producer, str) or len(producer) != 40:
        raise Task11VerificationError("producer source commit missing")
    if manifest.get("base_commit") != BASE_COMMIT:
        raise Task11VerificationError("base commit substitution")
    command_file = json.loads(_read_regular_file(output_dir / "execution_command.json"))
    exit_file = json.loads(_read_regular_file(output_dir / "execution_exit.json"))
    stdout = _stdout_fields(output_dir / "run_stdout.log")
    command = manifest.get("execution_command")
    if not isinstance(command, list):
        raise Task11VerificationError("execution command missing")
    _verify_exact_command([str(item) for item in command])
    if command_file.get("command") != command:
        raise Task11VerificationError("execution_command.json command mismatch")
    if command_file != exit_file:
        raise Task11VerificationError("command and exit execution records differ")
    invocation = manifest.get("invocation_id")
    if (
        invocation != FINAL_INVOCATION_ID
        or command_file.get("invocation_id") != invocation
        or exit_file.get("invocation_id") != invocation
        or stdout.get("invocation_id") != invocation
    ):
        raise Task11VerificationError("invocation mismatch across command/exit/stdout/manifest")
    if (
        command_file.get("producer_source_commit") != producer
        or exit_file.get("producer_source_commit") != producer
        or stdout.get("producer_source_commit") != producer
    ):
        raise Task11VerificationError(
            "producer source commit mismatch across command/exit/stdout/manifest"
        )
    if (
        manifest.get("execution_exit_status") != 0
        or command_file.get("exit_status") != 0
        or exit_file.get("exit_status") != 0
        or stdout.get("exit_status") != "0"
    ):
        raise Task11VerificationError("execution exit status is not zero")
    start, end = (
        _timestamp(manifest.get("start_timestamp"), "manifest start"),
        _timestamp(manifest.get("end_timestamp"), "manifest end"),
    )
    generated, now = _timestamp(manifest.get("generated_at"), "generated"), datetime.now(UTC)
    if (
        start > end
        or end > generated
        or generated - end > timedelta(minutes=1)
        or generated > now + timedelta(seconds=5)
    ):
        raise Task11VerificationError("reversed or future timestamps")
    for payload, label in ((command_file, "command"), (exit_file, "exit")):
        if (
            _timestamp(payload.get("start_timestamp"), f"{label} start") != start
            or _timestamp(payload.get("end_timestamp"), f"{label} end") != end
        ):
            raise Task11VerificationError("timestamp mismatch/backfill across evidence")
    if (
        _timestamp(stdout.get("start"), "stdout start") != start
        or _timestamp(stdout.get("end"), "stdout end") != end
    ):
        raise Task11VerificationError("stdout timestamp mismatch/backfill")
    for path in (
        candidate
        for candidate in output_dir.rglob("*")
        if candidate.is_file()
        and candidate.name != "TASK11_EVIDENCE_MANIFEST.json"
        and not candidate.is_symlink()
    ):
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified < start - timedelta(seconds=5) or modified > generated + timedelta(seconds=5):
            raise Task11VerificationError("timestamp backfill inconsistent with file mtime")
    if manifest.get("component_inventory") != COMPONENT_INVENTORY:
        raise Task11VerificationError("component source inventory incomplete")
    current_inventory = _source_inventory(repository_root)
    if manifest.get("source_inventory") != current_inventory:
        raise Task11VerificationError("source inventory differs from current executable source")
    if manifest.get("source_bundle_sha256") != canonical_sha256(current_inventory):
        raise Task11VerificationError("source bundle hash mismatch")
    frozen = verify_frozen_inputs(repository_root)
    if manifest.get("frozen_input_hashes") != frozen:
        raise Task11VerificationError("frozen input hash mismatch")
    expected_split = canonical_sha256(
        {
            "contexts": GAP_CONTEXTS,
            "budgets": CONTEXT_BUDGETS,
            "validation": VALIDATION_REPLICATE_SEEDS,
            "confirmatory": CONFIRMATORY_REPLICATE_SEEDS,
        }
    )
    if manifest.get("dataset_seed_split_hash") != expected_split:
        raise Task11VerificationError("dataset/seed/budget binding mismatch")
    if manifest.get("environment") != dependency_snapshot(repository_root):
        raise Task11VerificationError("runtime environment substitution")
    actual_artifacts = {
        path.relative_to(output_dir).as_posix(): sha256_file(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "TASK11_EVIDENCE_MANIFEST.json" and not path.is_symlink()
    }
    if manifest.get("artifact_hashes") != actual_artifacts:
        raise Task11VerificationError("artifact set/hash bundle mismatch")
    if manifest.get("stdout_sha256") != sha256_file(output_dir / "run_stdout.log") or manifest.get(
        "stderr_sha256"
    ) != sha256_file(output_dir / "run_stderr.log"):
        raise Task11VerificationError("stdout/stderr hash mismatch")
    preflight = manifest.get("preflight_working_tree_status")
    if not isinstance(preflight, list) or not all(isinstance(line, str) for line in preflight):
        raise Task11VerificationError("preflight working-tree status missing")
    if manifest.get("preflight_working_tree_clean") is not (not preflight):
        raise Task11VerificationError("preflight clean-tree flag disagrees with recorded status")
    postrun = manifest.get("postrun_working_tree_drift")
    if not isinstance(postrun, list) or not all(isinstance(line, str) for line in postrun):
        raise Task11VerificationError("postrun working-tree status missing")
    if manifest.get("postrun_drift_only_output_artifacts") is not False:
        raise Task11VerificationError("dirty local diagnostic cannot claim output-only drift")
    from itertools import chain

    traces = chain(
        iter_jsonl(output_dir / "raw_traces/task11_g1_full_budget_raw_traces.jsonl.gz"),
        iter_jsonl(output_dir / "raw_traces/task11_g2_full_budget_raw_traces.jsonl.gz"),
    )
    reported = json.loads(_read_regular_file(output_dir / "task11_recomputed_results.json"))
    for flag in (
        "formal_binding_resolved",
        "task_12_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if reported.get(flag) is not False:
            raise Task11VerificationError(f"reported result cannot set {flag}")
    recomputed = verify_recomputed_result(reported, traces, fresh_replay=True)
    raw_hashes = {
        "G1": sha256_file(output_dir / "raw_traces/task11_g1_full_budget_raw_traces.jsonl.gz"),
        "G2": sha256_file(output_dir / "raw_traces/task11_g2_full_budget_raw_traces.jsonl.gz"),
    }
    expected_report = render_diagnostic_report(recomputed, raw_hashes, producer).encode()
    if _read_regular_file(output_dir / "TASK11_RESAMPLING_DIAGNOSTIC_REPORT.md") != expected_report:
        raise Task11VerificationError("diagnostic report differs from canonical recomputation")
    if (
        stdout.get("condition_count") != str(recomputed["condition_count"])
        or stdout.get("trace_count") != str(recomputed["trace_count"])
        or stdout.get("raw_only_verification_gate") != "true"
        or stdout.get("fresh_source_replay_gate") != "true"
    ):
        raise Task11VerificationError("stdout result/gate claims differ from recomputation")
    for flag in (
        "formal_binding_resolved",
        "task_12_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if stdout.get(flag) != "false":
            raise Task11VerificationError(f"stdout cannot set or omit {flag}=false")
    for name in ("TASK11_ADVERSARIAL_AUDIT_ROUND1.md", "TASK11_ADVERSARIAL_AUDIT_ROUND2.md"):
        audit = _read_regular_file(output_dir / name).decode()
        if "Coverage: partial adversarial coverage." not in audit:
            raise Task11VerificationError("audit report overstates or omits partial coverage")
        if any(
            forbidden in audit
            for forbidden in (
                "formal_binding_resolved=true",
                "task_12_unlocked=true",
                "seven_operator_ablation_authorized=true",
                "FORMAL PASS",
            )
        ):
            raise Task11VerificationError("audit report attempts formal authority escalation")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
