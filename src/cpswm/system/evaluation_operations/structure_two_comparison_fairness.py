"""Executable frozen-contract checks and descriptive fairness evidence for window two.

These checks are part of the fresh audit, not a standalone authenticity verifier.
No production operator or registered comparison policy is changed here.
"""

from __future__ import annotations

import dis
import json
import sys
from collections import Counter
from itertools import product
from statistics import mean
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations import structure_two_p5_three_arm_death_test as base
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
    _locations,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import P5ComparisonArm
from cpswm.system.reproducibility import content_sha256, content_uuid


class SplitAccess:
    """Check actual dataset calls, not just the selection receipt's declared IDs."""

    def __init__(self, dataset: Any, split: Split) -> None:
        self.dataset = dataset
        self.split = split
        self.allowed = {e.episode_id for e in dataset.visible_episodes(split)}
        self.events: list[dict[str, Any]] = []

    def visible_episodes(self, split: Split) -> Any:
        if split != self.split:
            raise ValueError(f"FAIRNESS_SPLIT_ACCESS: {self.split} requested {split}")
        episodes = self.dataset.visible_episodes(split)
        self.events.append(
            {
                "kind": "visible",
                "split": split.value,
                "episodes": [str(e.episode_id) for e in episodes],
            }
        )
        return episodes

    def truth_for(self, episode_id: Any) -> Any:
        if episode_id not in self.allowed:
            raise ValueError(f"FAIRNESS_TRUTH_SPLIT: {self.split}:{episode_id}")
        if self.split != Split.TRAIN:
            raise ValueError("FAIRNESS_EARLY_TRUTH: scoring requires a committed typed action")
        self.events.append({"kind": "training_truth", "episode_id": str(episode_id)})
        return self.dataset.truth_for(episode_id)

    def score_committed(self, episode: Any, step: Any, posterior: Any, action: Any) -> Any:
        if episode.episode_id not in self.allowed:
            raise ValueError("FAIRNESS_TRUTH_SPLIT: scoring episode outside allowed split")
        check_decoded(posterior, action, step)
        if posterior.episode_id != episode.episode_id:
            raise ValueError("FAIRNESS_COMMIT_EPISODE: action/episode mismatch")
        # This is the concrete action commitment; truth lookup follows it.
        self.events.append(
            {
                "kind": "score_after_commit",
                "episode_id": str(episode.episode_id),
                "step_id": str(step.step_id),
                "arm": posterior.arm.value,
                "search": str(action.search_plan[0].location_id),
                "put_back": str(action.put_back_action.location_id),
            }
        )
        return self.dataset.truth_for(episode.episode_id).truth_by_step[step.step_id]


def check_decoded(posterior: Any, action: Any, step: Any) -> None:
    """Independent rule check over actual decoder output, including all SEARCH ties."""
    if (
        posterior.step_id != step.step_id
        or action.source_update_id != step.step_id
        or posterior.source_visible_step_sha256 != content_sha256(step)
        or action.belief_state_sha256 != posterior.belief_state_sha256
    ):
        raise ValueError("FAIRNESS_COMMIT_IDENTITY: step/input/state mismatch")
    search = sorted(
        posterior.current_location_distribution, key=lambda x: (-x.probability, str(x.location_id))
    )
    habit = sorted(
        posterior.owner_habit_location_distribution,
        key=lambda x: (-x.probability, str(x.location_id)),
    )
    if [x.location_id for x in action.search_plan] != [
        x.location_id for x in search
    ] or action.put_back_action.location_id != habit[0].location_id:
        raise ValueError("FAIRNESS_DECODER_RULE: output differs from shared posterior ranking")


def check_receipt(packet: Any, receipt: Any) -> None:
    expected = base.CIAVConsumptionReceipt.seal(
        arm=receipt.arm,
        packet=packet,
        consumer_state_before_sha256=receipt.consumer_state_before_sha256,
        consumer_state_after_sha256=receipt.consumer_state_after_sha256,
        closure_kind=receipt.closure_kind,
    )
    if receipt != expected:
        raise ValueError("FAIRNESS_PACKET_RESOURCE: receipt fields differ from actual packet")


def check_step(packet: Any, step: Any, posteriors: list[Any], receipts: list[Any]) -> None:
    """Strict common input/support checks at the consumer boundary, before truth."""
    if len(posteriors) != 3 or {p.arm for p in posteriors} != set(P5ComparisonArm):
        raise ValueError("FAIRNESS_ARMS: exactly one posterior for each registered arm required")
    base.verify_matched_consumption(receipts)
    for receipt in receipts:
        check_receipt(packet, receipt)
    if any(p.location_support != posteriors[0].location_support for p in posteriors):
        raise ValueError("FAIRNESS_SUPPORT: arm candidate support/order differs")
    if any(
        p.source_visible_step_sha256 != content_sha256(step)
        or p.step_id != step.step_id
        or p.episode_id != packet.episode_id
        for p in posteriors
    ):
        raise ValueError("FAIRNESS_VISIBLE_INPUT: consumer input differs from released step")
    if any(r.packet_sha256 != packet.packet_sha256 for r in receipts):
        raise ValueError("FAIRNESS_PACKET: receipt differs from actual released packet")


def validation_errors(access: SplitAccess, episode: Any, state: Any) -> tuple[float, float]:
    """Window-two replacement for the combined pre-decode truth/scoring consumer."""
    schedule = base._episode_schedule_commitment(episode)
    run_id = content_uuid(
        base.PROTOCOL_ID, {"episode_id": str(episode.episode_id), "arm": state.arm.value}
    )
    search_errors = put_errors = 0
    for index, step in enumerate(episode.steps):
        packet = base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        receipt = state.consume_matched_ciav_packet(packet, step, step_index=index)
        check_receipt(packet, receipt)
        posterior = state.predict_location_posteriors(packet)
        action = posterior.decode(
            step_index=index,
            run_execution_id=run_id,
            visible_observation=step.model_dump(mode="json"),
        )
        truth = access.score_committed(episode, step, posterior, action)
        search_errors += action.search_plan[0].location_id != truth.true_location
        put_errors += action.put_back_action.location_id != truth.true_owner_habit_location
    return search_errors / len(episode.steps), put_errors / len(episode.steps)


def validation_selection(dataset: Any, config: Any, material: Any) -> tuple[Any, ...]:
    """Same frozen grid, fit functions, ranking and model cache; safe scoring order."""
    train_ids = {e.episode_id for e in dataset.visible_episodes(Split.TRAIN)}
    if set(material.training_episode_ids) != train_ids:
        raise ValueError("FAIRNESS_TRAINING_IDS: fitted material split differs")
    access = SplitAccess(dataset, Split.VALIDATION)
    validation = access.visible_episodes(Split.VALIDATION)
    lc = config["learned_two_stage"]
    if any(
        config[k]["selection_metric"] != "validation_put_back_error_rate"
        for k in ("learned_two_stage", "amg")
    ):
        raise ValueError("FAIRNESS_SELECTION_OBJECTIVE: frozen PUT_BACK objective changed")
    cache = {}
    learned_trials: list[dict[str, Any]] = []
    amg_trials: list[dict[str, Any]] = []
    fit_costs = []
    for width, lr, l2 in product(lc["base_widths"], lc["learning_rates"], lc["l2_values"]):
        key = (int(width), float(lr), float(l2))
        model = base._fit_learned_model(
            material, {"base_width": key[0], "learning_rate": key[1], "l2": key[2]}
        )
        cache[key] = model
        fit_costs.append(
            {
                "parameters": list(key),
                "rows": len(material.raw),
                "training_multiply_adds_head_only": model.training_multiply_adds,
                "active_parameters": model.active_parameter_count,
            }
        )
        for smoothing in lc["location_smoothing_values"]:
            metrics = [
                validation_errors(
                    access,
                    e,
                    base.LearnedTwoStageLocationAdapter(
                        e,
                        model=model,
                        location_successes=material.location_successes,
                        location_totals=material.location_totals,
                        smoothing=float(smoothing),
                    ),
                )
                for e in validation
            ]
            learned_trials.append(
                {
                    "parameters": {
                        "base_width": key[0],
                        "learning_rate": key[1],
                        "l2": key[2],
                        "location_smoothing": float(smoothing),
                    },
                    "validation_put_back_error_rate": mean(m[1] for m in metrics),
                    "validation_search_error_rate": mean(m[0] for m in metrics),
                }
            )
    selected = min(
        learned_trials,
        key=lambda r: (
            r["validation_put_back_error_rate"],
            json.dumps(r["parameters"], sort_keys=True),
        ),
    )
    params = selected["parameters"]
    for parameter in config["amg"]["parameter_values"]:
        metrics = [
            validation_errors(access, e, base.AMGLocationAdapter(e, parameter=float(parameter)))
            for e in validation
        ]
        amg_trials.append(
            {
                "parameter": float(parameter),
                "validation_put_back_error_rate": mean(m[1] for m in metrics),
                "validation_search_error_rate": mean(m[0] for m in metrics),
            }
        )
    amg = min(amg_trials, key=lambda r: (r["validation_put_back_error_rate"], r["parameter"]))
    receipt = {
        "selection_metric": "validation_put_back_error_rate",
        "training_episode_ids": [str(i) for i in material.training_episode_ids],
        "validation_episode_ids": [str(e.episode_id) for e in validation],
        "test_episode_ids_seen": [],
        "learned_trials": learned_trials,
        "selected_learned_parameters": params,
        "amg_trials": amg_trials,
        "selected_amg_parameter": amg["parameter"],
    }
    receipt["content_sha256"] = content_sha256(receipt)
    evidence = {
        "access_events": access.events,
        "model_fits": fit_costs,
        "fit_material_sha256": content_sha256(
            {
                "raw": material.raw.tolist(),
                "cause": material.cause.tolist(),
                "event": material.event.tolist(),
                "successes": material.location_successes.tolist(),
                "totals": material.location_totals.tolist(),
            }
        ),
    }
    return (
        receipt,
        cache[(params["base_width"], params["learning_rate"], params["l2"])],
        params["location_smoothing"],
        amg["parameter"],
        evidence,
    )


class ConsumerProbe:
    """Bounded real call/return probe. Records accessed attribute opcodes and values.

    Executed LOAD_ATTR/LOAD_METHOD names identify the selected code path, not a
    security taint proof. This probe never modifies a function or injects outputs.
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.accesses: Counter[str] = Counter()
        self.instructions: dict[Any, Any] = {}
        self.previous: Any = None
        self.targets = {
            base._feature_row.__code__,
            base._transition.__code__,
            _locations.__code__,
            _AMGOpenWorldMethod.observe.__code__,
        }

    def trace(self, frame: Any, event: str, arg: Any) -> Any:
        code = frame.f_code
        if code not in self.targets:
            return None
        symbol = code.co_qualname
        if event == "call":
            frame.f_trace_opcodes = True
            self.instructions.setdefault(code, {i.offset: i for i in dis.get_instructions(code)})
        elif event == "opcode":
            instruction = self.instructions[code].get(frame.f_lasti)
            if instruction and instruction.opname in {"LOAD_ATTR", "LOAD_METHOD"}:
                self.accesses[f"{symbol}:{instruction.argval}"] += 1
        elif event == "return":
            record: dict[str, Any] = {"symbol": symbol}
            if "step" in frame.f_locals:
                record["step_id"] = str(frame.f_locals["step"].step_id)
            if code == base._feature_row.__code__:
                record["feature_values"] = list(arg)
            elif code == _locations.__code__:
                record["support"] = list(map(str, arg))
                ep = frame.f_locals["episode"]
                record["known_location_ids"] = list(map(str, ep.known_location_ids))
                record["episode_steps_available"] = len(ep.steps)
            elif code == base._transition.__code__:
                record["evidence"] = [type(e).__name__ for e in arg.evidence]
                record["actor_prior"] = dict(arg.actor_prior)
                record["before_detected"] = str(arg.before.detected_location_id)
                record["after_detected"] = str(arg.after.detected_location_id)
            else:
                local = frame.f_locals
                record["actor_likelihoods"] = local.get("actor_likelihoods", {})
                record["mechanism_likelihoods"] = {
                    str(k): v for k, v in local.get("mechanism_probabilities", {}).items()
                }
                record["role_likelihoods"] = {str(k): v for k, v in local.get("roles", {}).items()}
            self.records.append(record)
        return self.trace

    def __enter__(self) -> ConsumerProbe:
        self.previous = sys.gettrace()
        if self.previous is not None:
            raise ValueError("FAIRNESS_PROBE_EXISTING_TRACER: refusing to replace active tracer")
        sys.settrace(self.trace)
        return self

    def __exit__(self, *args: Any) -> None:
        sys.settrace(self.previous)

    def result(self) -> dict[str, Any]:
        return {
            "scope": "first fixed opened test episode, actual consumer calls; not timing",
            "executed_attribute_reads": dict(sorted(self.accesses.items())),
            "returns": self.records,
        }


def findings(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep descriptive differences separate from passing the named checks."""
    from cpswm.system.evaluation_operations.structure_two_comparison_audit import AMG, ARMS, P5

    return {
        "development_only": True,
        "comparison_fairness": "NOT_ESTABLISHED",
        "scientific_validity": "NOT_ESTABLISHED",
        "steps_checked": len(rows),
        "checks": [
            "three distinct arms",
            "actual packet and visible hash",
            "same support/order",
            "shared decoder ranking and ties",
            "test truth after three commits",
        ],
        "observations": {
            "future_support_steps": sum(r["future_support_count"] > 0 for r in rows),
            "search_equal_steps": sum(
                all(r["arms"][a]["current"] == r["arms"][P5]["current"] for a in ARMS) for r in rows
            ),
            "amg_missing_owner_steps": sum(r["fairness_step"]["amg_owner_missing"] for r in rows),
            "p5_commit_counts": dict(
                Counter(
                    str(r["raw_state"]["p5_readouts"]["state_counts"]["_committed_events"])
                    for r in rows
                )
            ),
            "full_fast_different_steps": sum(
                r["arms"][P5]["put_back"]
                != r["alternative_readouts_development_only"]["fast"]["put_back"]
                for r in rows
            ),
            "p5_minus_amg_errors": sum(
                r["arms"][P5]["put_back_error"] - r["arms"][AMG]["put_back_error"] for r in rows
            ),
        },
        "pending_user_decisions": [
            "public map vs causal prefix support permission",
            "common missing-owner prior",
            "native SEARCH head and search budget",
            "evidence feature entitlement vs identical feature consumption",
            "capacity/training/inference budgets",
            "long-memory and feedback challenge distribution",
        ],
    }
