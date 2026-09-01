"""Method-free gates that check whether a benchmark target can answer a question.

Two gates live here.  Neither one runs, tunes, or scores any research method, so
neither can be steered toward a preferred winner.

``Gate A`` (trivial-rule ceiling) asks whether a target leaves room for a method
at all.  It scores a fixed, published set of rules that carry no learned state
and no model, and it separately measures whether the target's *update law* is
reproduced exactly once an oracle supplies the law's trigger.  A target whose
law recurrence is 1.0 contains no dynamics to model: whatever difficulty remains
is trigger inference, and a comparison run on that target measures only trigger
inference no matter what the competing systems claim to do.

``Gate B`` (arm distinguishability) asks whether an experiment's arms are
actually different.  Arms whose per-episode prediction sequences hash to the
same value cannot be separated by any endpoint computed from those predictions;
a confidence interval between two such arms is an artefact of cost bookkeeping,
not evidence about method behaviour.

Both gates are diagnostics.  Passing them does not make a benchmark valid, and
failing them does not invalidate the underlying scientific question -- it says
the current instrument cannot be used to answer it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "task-nontriviality-and-arm-distinguishability-gates@0.1"

TRUTH_TRIGGER_RULE = "sticky_true_trigger_law"
SINGLE_FEATURE_RULE = "single_visible_feature_lookup"
TRUTH_HISTORY_RULES = frozenset(
    {TRUTH_TRIGGER_RULE, SINGLE_FEATURE_RULE, "persist_previous_target"}
)

STATE_TRACKING_CRITERIA = (
    "a1_trivial_ceiling_leaves_headroom",
    "a2_update_law_is_not_trivial",
    "a3_target_carries_context_structure",
    "a4_task_is_more_than_trigger_inference",
)
CLASSIFICATION_CRITERIA = (
    "a1_trivial_ceiling_leaves_headroom",
    "a5_target_is_not_a_single_feature_lookup",
)


@dataclass(frozen=True, slots=True)
class TargetStep:
    """One scored step of a target stream.

    ``observed_value`` and ``visible_trigger`` are model-visible.  ``target`` and
    ``true_trigger`` are evaluator-only and are never handed to a visible-only
    rule.
    """

    context_key: str
    candidates: tuple[str, ...]
    observed_value: str | None
    visible_trigger: bool
    target: str
    true_trigger: bool


@dataclass(frozen=True, slots=True)
class TargetStream:
    stream_id: str
    stratum: str
    steps: tuple[TargetStep, ...]


@dataclass(frozen=True, slots=True)
class GateAThresholds:
    """Author-chosen defaults.  Every protocol must restate and justify these.

    They are deliberately not tuned to any existing result; they encode
    "a method needs somewhere to go" and "the target must not be a one-liner".
    """

    min_trivial_ceiling_error: float = 0.10
    max_law_recurrence: float = 0.98
    min_context_gain: float = 0.01
    max_trigger_inference_share: float = 0.90


class _Rule:
    """Visible-only prediction rule with no learned parameters."""

    name: str = "rule"
    uses_truth: bool = False

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        raise NotImplementedError

    def observe(self, step: TargetStep) -> None:
        """Consume the model-visible part of the current step before predicting."""

    def predict(self, step: TargetStep) -> str:
        raise NotImplementedError

    def settle(self, step: TargetStep) -> None:
        """Consume the scored target after prediction (truth rules only)."""


class _ConstantFirstCandidate(_Rule):
    name = "constant_first_candidate"

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._value = first_candidates[0]

    def predict(self, step: TargetStep) -> str:
        return self._value


class _GlobalModeObserved(_Rule):
    name = "global_mode_observed"

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._counts: Counter[str] = Counter()
        self._fallback = first_candidates[0]

    def observe(self, step: TargetStep) -> None:
        if step.observed_value is not None:
            self._counts[step.observed_value] += 1

    def predict(self, step: TargetStep) -> str:
        if not self._counts:
            return self._fallback
        return min(self._counts.items(), key=lambda item: (-item[1], item[0]))[0]


class _LastObserved(_Rule):
    name = "last_observed_value"

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._value = first_candidates[0]

    def observe(self, step: TargetStep) -> None:
        if step.observed_value is not None:
            self._value = step.observed_value

    def predict(self, step: TargetStep) -> str:
        return self._value


class _StickyVisibleTrigger(_Rule):
    name = "sticky_visible_trigger_law"

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._value = first_candidates[0]

    def observe(self, step: TargetStep) -> None:
        if step.visible_trigger and step.observed_value is not None:
            self._value = step.observed_value

    def predict(self, step: TargetStep) -> str:
        return self._value


class _PerContextModeObserved(_Rule):
    name = "per_context_mode_observed"

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._by_context: dict[str, Counter[str]] = {}
        self._global: Counter[str] = Counter()
        self._fallback = first_candidates[0]

    def observe(self, step: TargetStep) -> None:
        if step.observed_value is None:
            return
        self._by_context.setdefault(step.context_key, Counter())[step.observed_value] += 1
        self._global[step.observed_value] += 1

    def predict(self, step: TargetStep) -> str:
        bucket = self._by_context.get(step.context_key)
        source = bucket if bucket else self._global
        if not source:
            return self._fallback
        return min(source.items(), key=lambda item: (-item[1], item[0]))[0]


class _StickyTrueTrigger(_Rule):
    """Evaluator-side law probe: the same one-line law, given the true trigger."""

    name = TRUTH_TRIGGER_RULE
    uses_truth = True

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._value = first_candidates[0]

    def observe(self, step: TargetStep) -> None:
        if step.true_trigger and step.observed_value is not None:
            self._value = step.observed_value

    def predict(self, step: TargetStep) -> str:
        return self._value


class _PersistPreviousTarget(_Rule):
    """Evaluator-side autocorrelation probe."""

    name = "persist_previous_target"
    uses_truth = True

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._value = first_candidates[0]

    def predict(self, step: TargetStep) -> str:
        return self._value

    def settle(self, step: TargetStep) -> None:
        self._value = step.target


class _SingleFeatureLookup(_Rule):
    """Evaluator-side probe: an online lookup table keyed on one visible feature.

    It reads past targets only, never the current one, so it is a legitimate
    online predictor.  It is still listed as truth-using because a *method* is
    not normally allowed a free per-step label oracle for its own history in
    these protocols.  Near-zero error here means the target is a lookup table on
    one visible field, whatever a method claims to model.
    """

    name = SINGLE_FEATURE_RULE
    uses_truth = True

    def reset(self, first_candidates: tuple[str, ...]) -> None:
        self._table: dict[str, Counter[str]] = {}
        self._fallback: Counter[str] = Counter()
        self._default = first_candidates[0]
        self._key: str | None = None

    def observe(self, step: TargetStep) -> None:
        self._key = step.observed_value if step.observed_value is not None else "__missing__"

    def predict(self, step: TargetStep) -> str:
        bucket = self._table.get(self._key or "__missing__")
        source = bucket if bucket else self._fallback
        if not source:
            return self._default
        return min(source.items(), key=lambda item: (-item[1], item[0]))[0]

    def settle(self, step: TargetStep) -> None:
        key = self._key or "__missing__"
        self._table.setdefault(key, Counter())[step.target] += 1
        self._fallback[step.target] += 1


def _rule_factories() -> tuple[type[_Rule], ...]:
    return (
        _ConstantFirstCandidate,
        _GlobalModeObserved,
        _LastObserved,
        _StickyVisibleTrigger,
        _PerContextModeObserved,
        _StickyTrueTrigger,
        _PersistPreviousTarget,
        _SingleFeatureLookup,
    )


def _score_rule(rule: _Rule, streams: Sequence[TargetStream]) -> dict[str, Any]:
    errors = 0
    total = 0
    per_stratum_err: dict[str, list[int]] = {}
    for stream in streams:
        if not stream.steps:
            continue
        rule.reset(stream.steps[0].candidates)
        bucket = per_stratum_err.setdefault(stream.stratum, [0, 0])
        for step in stream.steps:
            rule.observe(step)
            wrong = int(rule.predict(step) != step.target)
            rule.settle(step)
            errors += wrong
            total += 1
            bucket[0] += wrong
            bucket[1] += 1
    return {
        "rule": rule.name,
        "uses_evaluator_truth": rule.uses_truth,
        "error_rate": errors / total if total else 0.0,
        "scored_steps": total,
        "per_stratum_error_rate": {
            key: (value[0] / value[1] if value[1] else 0.0)
            for key, value in sorted(per_stratum_err.items())
        },
    }


def _conditional_law_recurrence(streams: Sequence[TargetStream]) -> dict[str, Any]:
    """Rate at which the target reproduces its own one-line update law.

    This generalises the statistic the 2026-08-28 AMG interface audit reported.
    Steps are split three ways, because they answer different questions:

    ``on_trigger_observed``
        the law fires and can see where the object went;
    ``on_trigger_unobserved``
        the law fires but nothing was seen, so no rule of any kind can follow;
    ``off_trigger``
        the law does not fire and the target should persist.

    ``observed_step_rate`` combines the first and third buckets: it is the rate
    at which a two-line law reproduces the target *wherever the law is
    executable at all*.  At 1.0 the benchmark contains no dynamics to model, and
    the residual error every arm reports is irreducible missing observation, not
    a modelling gap a better world model could close.
    """

    buckets = {
        "on_trigger_observed": [0, 0],
        "on_trigger_unobserved": [0, 0],
        "off_trigger": [0, 0],
    }
    observed_match = observed_total = 0
    for stream in streams:
        previous: str | None = None
        for step in stream.steps:
            if step.true_trigger and step.observed_value is not None:
                key, expected = "on_trigger_observed", step.observed_value
            elif step.true_trigger:
                key, expected = "on_trigger_unobserved", previous
            else:
                key, expected = "off_trigger", previous
            if expected is not None:
                match = int(step.target == expected)
                buckets[key][0] += match
                buckets[key][1] += 1
                if key != "on_trigger_unobserved":
                    observed_match += match
                    observed_total += 1
            previous = step.target
    report: dict[str, Any] = {
        f"{name}_rate": (value[0] / value[1] if value[1] else 0.0)
        for name, value in buckets.items()
    }
    report.update({f"{name}_steps": value[1] for name, value in buckets.items()})
    report["observed_step_rate"] = observed_match / observed_total if observed_total else 0.0
    report["observed_steps"] = observed_total
    return report


def run_gate_a(
    streams: Sequence[TargetStream],
    *,
    target_name: str,
    target_kind: str = "state_tracking",
    thresholds: GateAThresholds | None = None,
) -> dict[str, Any]:
    """Score every trivial rule on a target stream and apply Gate A.

    ``target_kind`` selects which criteria bind.  A state-tracking target must
    carry dynamics worth modelling; a classification target need not, so only
    the headroom and lookup-table criteria bind for it.  Every statistic is
    reported for both kinds, so a reader can apply their own reading.
    """

    limits = thresholds or GateAThresholds()
    if target_kind not in {"state_tracking", "classification"}:
        raise ValueError(f"unknown target_kind {target_kind!r}")
    if not streams:
        raise ValueError("gate A requires at least one target stream")
    scored = [_score_rule(factory(), streams) for factory in _rule_factories()]
    by_name = {item["rule"]: item for item in scored}

    visible = [item for item in scored if not item["uses_evaluator_truth"]]
    ceiling = min(visible, key=lambda item: (item["error_rate"], item["rule"]))
    trivial_ceiling_error = float(ceiling["error_rate"])

    law_error = float(by_name[TRUTH_TRIGGER_RULE]["error_rate"])
    law_recurrence = 1.0 - law_error

    context_free = min(
        (item["error_rate"] for item in visible if item["rule"] != _PerContextModeObserved.name),
        default=1.0,
    )
    context_gain = float(context_free) - float(by_name[_PerContextModeObserved.name]["error_rate"])

    trigger_share = (
        (trivial_ceiling_error - law_error) / trivial_ceiling_error
        if trivial_ceiling_error > 0.0
        else 0.0
    )

    lookup_error = float(by_name[SINGLE_FEATURE_RULE]["error_rate"])
    conditional = _conditional_law_recurrence(streams)
    conditional_rate = float(conditional["observed_step_rate"])

    criteria = {
        "a1_trivial_ceiling_leaves_headroom": trivial_ceiling_error
        >= limits.min_trivial_ceiling_error,
        "a2_update_law_is_not_trivial": conditional_rate <= limits.max_law_recurrence,
        "a3_target_carries_context_structure": context_gain >= limits.min_context_gain,
        "a4_task_is_more_than_trigger_inference": trigger_share
        <= limits.max_trigger_inference_share,
        "a5_target_is_not_a_single_feature_lookup": lookup_error
        >= limits.min_trivial_ceiling_error,
    }
    binding = (
        STATE_TRACKING_CRITERIA if target_kind == "state_tracking" else CLASSIFICATION_CRITERIA
    )
    return {
        "protocol": PROTOCOL_ID,
        "gate": "trivial_rule_ceiling",
        "target_name": target_name,
        "target_kind": target_kind,
        "binding_criteria": list(binding),
        "stream_count": len(streams),
        "scored_steps": int(ceiling["scored_steps"]),
        "thresholds": {
            "min_trivial_ceiling_error": limits.min_trivial_ceiling_error,
            "max_law_recurrence": limits.max_law_recurrence,
            "min_context_gain": limits.min_context_gain,
            "max_trigger_inference_share": limits.max_trigger_inference_share,
        },
        "rules": scored,
        "best_visible_trivial_rule": ceiling["rule"],
        "trivial_ceiling_error": trivial_ceiling_error,
        "update_law_error_with_true_trigger": law_error,
        "update_law_recurrence_with_true_trigger": law_recurrence,
        "conditional_update_law_recurrence": conditional,
        "context_conditioning_gain": context_gain,
        "trigger_inference_share_of_remaining_error": trigger_share,
        "single_visible_feature_lookup_error": lookup_error,
        "criteria": criteria,
        "gate_a_passed": all(criteria[name] for name in binding),
    }


@dataclass(frozen=True, slots=True)
class ArmPredictionTrace:
    """One arm's complete, ordered prediction record over the scored episodes."""

    arm: str
    episode_predictions: tuple[tuple[str, tuple[str, ...]], ...] = field(default=())


def run_gate_b(
    traces: Iterable[ArmPredictionTrace],
    *,
    min_pairwise_prediction_disagreement_rate: float = 0.0,
    min_episode_fraction_with_multiple_arm_trajectories: float = 0.0,
) -> dict[str, Any]:
    """Check exact collisions and whether arm differences are non-negligible.

    The zero defaults preserve the original generic diagnostic.  A formal
    protocol should preregister positive thresholds so that changing one token
    cannot turn otherwise identical arms into a Gate-B pass.
    """

    materialised = list(traces)
    if len(materialised) < 2:
        raise ValueError("gate B requires at least two arms")
    for name, value in (
        (
            "min_pairwise_prediction_disagreement_rate",
            min_pairwise_prediction_disagreement_rate,
        ),
        (
            "min_episode_fraction_with_multiple_arm_trajectories",
            min_episode_fraction_with_multiple_arm_trajectories,
        ),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must lie in [0, 1]")
    digests: dict[str, str] = {}
    by_arm: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {}
    for trace in materialised:
        if trace.arm in by_arm:
            raise ValueError(f"duplicate gate B arm: {trace.arm}")
        by_arm[trace.arm] = trace.episode_predictions
        payload = [
            [episode_id, list(predictions)] for episode_id, predictions in trace.episode_predictions
        ]
        digests[trace.arm] = content_sha256(payload)

    groups: dict[str, list[str]] = {}
    for arm, digest in sorted(digests.items()):
        groups.setdefault(digest, []).append(arm)
    collisions = sorted(
        (sorted(arms) for arms in groups.values() if len(arms) > 1),
        key=lambda arms: arms[0],
    )
    arms = sorted(digests)
    pairwise = {
        f"{left}|{right}": digests[left] == digests[right]
        for index, left in enumerate(arms)
        for right in arms[index + 1 :]
    }
    reference_episode_ids = tuple(episode_id for episode_id, _ in by_arm[arms[0]])
    for arm in arms[1:]:
        episode_ids = tuple(episode_id for episode_id, _ in by_arm[arm])
        if episode_ids != reference_episode_ids:
            raise ValueError("gate B arms must share the same ordered episode ids")

    pairwise_disagreement_rates: dict[str, float] = {}
    for index, left in enumerate(arms):
        left_predictions = tuple(
            prediction for _, predictions in by_arm[left] for prediction in predictions
        )
        for right in arms[index + 1 :]:
            right_predictions = tuple(
                prediction for _, predictions in by_arm[right] for prediction in predictions
            )
            if len(left_predictions) != len(right_predictions):
                raise ValueError("gate B arms must have equal scored-step coverage")
            if not left_predictions:
                raise ValueError("gate B arm traces must contain scored predictions")
            disagreements = sum(
                left_item != right_item
                for left_item, right_item in zip(
                    left_predictions,
                    right_predictions,
                    strict=True,
                )
            )
            pairwise_disagreement_rates[f"{left}|{right}"] = disagreements / len(left_predictions)

    diverse_episode_count = 0
    for episode_index, _ in enumerate(reference_episode_ids):
        trajectories = {by_arm[arm][episode_index][1] for arm in arms}
        diverse_episode_count += len(trajectories) > 1
    diverse_episode_fraction = (
        diverse_episode_count / len(reference_episode_ids) if reference_episode_ids else 0.0
    )
    minimum_pairwise_disagreement_rate = min(pairwise_disagreement_rates.values())
    criteria = {
        "b1_no_two_arms_produce_identical_predictions": not collisions,
        "b2_every_arm_pair_has_preregistered_disagreement": (
            minimum_pairwise_disagreement_rate >= min_pairwise_prediction_disagreement_rate
        ),
        "b3_multiple_arm_trajectories_cover_preregistered_episode_fraction": (
            diverse_episode_fraction >= min_episode_fraction_with_multiple_arm_trajectories
        ),
    }
    return {
        "protocol": PROTOCOL_ID,
        "gate": "arm_distinguishability",
        "declared_arm_count": len(arms),
        "distinguishable_arm_count": len(groups),
        "prediction_digests": digests,
        "identical_arm_groups": collisions,
        "pairwise_identical": pairwise,
        "pairwise_prediction_disagreement_rates": pairwise_disagreement_rates,
        "minimum_pairwise_prediction_disagreement_rate": (minimum_pairwise_disagreement_rate),
        "episode_count_with_multiple_arm_trajectories": diverse_episode_count,
        "episode_fraction_with_multiple_arm_trajectories": diverse_episode_fraction,
        "thresholds": {
            "min_pairwise_prediction_disagreement_rate": (
                min_pairwise_prediction_disagreement_rate
            ),
            "min_episode_fraction_with_multiple_arm_trajectories": (
                min_episode_fraction_with_multiple_arm_trajectories
            ),
        },
        "criteria": criteria,
        "gate_b_passed": all(criteria.values()),
    }


def summarise_gate_reports(reports: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(reports)
    payload["protocol"] = PROTOCOL_ID
    payload["content_sha256"] = content_sha256(
        {key: value for key, value in sorted(payload.items()) if key != "content_sha256"}
    )
    return payload


__all__ = [
    "CLASSIFICATION_CRITERIA",
    "PROTOCOL_ID",
    "STATE_TRACKING_CRITERIA",
    "ArmPredictionTrace",
    "GateAThresholds",
    "TargetStep",
    "TargetStream",
    "run_gate_a",
    "run_gate_b",
    "summarise_gate_reports",
]
