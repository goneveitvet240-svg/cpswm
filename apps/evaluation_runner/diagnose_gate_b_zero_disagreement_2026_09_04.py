#!/usr/bin/env python3
"""Diagnose why Gate B v0.5 reports 0.0 pairwise disagreement between arms.

Companion to docs/experiments/structure_two_gate_b_zero_disagreement_diagnosis_2026-09-04.md.

The frozen-design loader is bypassed for ONE check only -- its source-bundle
digest -- which the tree already fails for a reason that predates this
diagnosis (see that document, section 7).  Everything that determines the
worlds (the distribution and the three seed lists) is read verbatim from the
frozen manifest, and section A asserts byte-identity against the signed v0.5
trace before any conclusion is drawn.

    python apps/evaluation_runner/diagnose_gate_b_zero_disagreement_2026_09_04.py \
        --sections A,B,C,D --rollouts 6
    python apps/evaluation_runner/diagnose_gate_b_zero_disagreement_2026_09_04.py \
        --sections E --slice 0:18
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
from dataclasses import replace as dataclass_replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations import (  # noqa: E402
    structure_two_strongest_neighbor_gate as neighbor,
)
from cpswm.system.evaluation_operations.project_two_dataset import (  # noqa: E402
    ProjectTwoDatasetSplit,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (  # noqa: E402
    _argmax_distribution,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (  # noqa: E402
    _rank_distribution as _rank_source,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (  # noqa: E402
    ARM_PARAMETERS,
    adapt_world_rollout,
    make_world_arm_state,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (  # noqa: E402
    StructureTwoWorldGeneratorV02,
    WorldDistributionConfig,
)

MANIFEST = ROOT / "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
TRACE_DIR = ROOT / "benchmarks/structure_two/gate_b_arm_traces_v0_5"
NEIGHBOUR_ARMS = (
    "active_dreaming_matched",
    "brainctl_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "care_no_action_regret",
    "care_wm",
)
ALL_ARMS = (
    *NEIGHBOUR_ARMS,
    "sequential_no_consolidation",
    "corrected_amg",
    "o_star_matched",
    "full_rerun",
)
B2_THRESHOLD = 0.01

_RANK_CAPTURE: list[dict] = []
_DECISION_CAPTURE: list[str] = []
_FORCED_DECISION: list[object] = [None]


def _install_probes() -> None:
    original_rank = neighbor._rank_distribution
    original_choose = neighbor.choose_neighbor_decision

    def rank_probe(values):
        _RANK_CAPTURE.append(dict(values))
        return original_rank(values)

    def choose_probe(arm, visible, parameter):
        decision = original_choose(arm, visible, parameter)
        _DECISION_CAPTURE.append(decision.action.value)
        if _FORCED_DECISION[0] is not None:
            return dataclass_replace(decision, action=_FORCED_DECISION[0])
        return decision

    neighbor._rank_distribution = rank_probe
    neighbor.choose_neighbor_decision = choose_probe


def build_rollouts() -> list[tuple[object, object]]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    split = payload["split_policy"]
    generator = StructureTwoWorldGeneratorV02(
        WorldDistributionConfig.from_manifest(payload["world_distribution"])
    )
    rollouts = []
    for world_seed in split["v0_5_validation_world_seeds_preregistered_not_generated"]:
        world = generator.sample_world(int(world_seed))
        for trajectory_seed in split["validation_trajectory_seeds"]:
            for observation_seed in split["validation_observation_seeds"]:
                rollouts.append(
                    (
                        world,
                        generator.generate_rollout(
                            world,
                            trajectory_seed=int(trajectory_seed),
                            observation_seed=int(observation_seed),
                        ),
                    )
                )
    return rollouts


def run_arm(rollouts, arm: str, *, forced=None, capture_distributions: bool = True):
    """Return (tokens, decisions, distributions) for one arm over ``rollouts``."""
    _FORCED_DECISION[0] = forced
    tokens: list[str] = []
    decisions: list[str] = []
    distributions: list[dict] = []
    for world, rollout in rollouts:
        dataset = adapt_world_rollout(world, rollout)
        episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
        state = make_world_arm_state(dataset, episode, arm)
        for step in episode.steps:
            state.observe(step)
            _RANK_CAPTURE.clear()
            _DECISION_CAPTURE.clear()
            before = int(getattr(state, "verification_count", 0))
            prediction = state.predict()
            after = int(getattr(state, "verification_count", 0))
            executed = int(after > before)
            tokens.append(
                f"verify={executed}|{prediction.put_back}>{prediction.search_order[0]}"
                if prediction.search_order
                else f"verify={executed}|{prediction.put_back}"
            )
            decisions.append(_DECISION_CAPTURE[-1] if _DECISION_CAPTURE else "none")
            if capture_distributions:
                distributions.append(dict(_RANK_CAPTURE[-1]) if _RANK_CAPTURE else {})
            state.feedback(step)
    _FORCED_DECISION[0] = None
    return tokens, decisions, distributions


def total_variation(left, right) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def top1(dist):
    return str(_rank_source(dist)[0]) if dist else ""


def top3(dist):
    return "|".join(str(key) for key in _rank_source(dist)[:3]) if dist else ""


def top4_2dp(dist):
    if not dist:
        return ""
    ordered = sorted(((str(k), v) for k, v in dist.items()), key=lambda kv: (-kv[1], kv[0]))
    return "|".join(f"{k}:{v:.2f}" for k, v in ordered[:4])


def section_a(rollouts) -> None:
    """Fidelity: the probe reproduces the signed trace byte for byte."""
    signed = json.loads((TRACE_DIR / "arm_active_dreaming_matched.json").read_text("utf-8"))
    signed_ids = [row[0] for row in signed["episode_predictions"]]
    assert rollouts[0][1].rollout_id == signed_ids[0], "regenerated world differs from Gate A"
    tokens, _, _ = run_arm(rollouts, "active_dreaming_matched", capture_distributions=False)
    reference = [p for _, preds in signed["episode_predictions"][: len(rollouts)] for p in preds]
    same = sum(1 for a, b in zip(reference, tokens, strict=True) if a == b)
    print(
        f"A  probe vs signed v0.5 trace: {same}/{len(reference)} tokens identical "
        f"({'PASS' if same == len(reference) else 'FAIL'})"
    )


def section_b(rollouts) -> None:
    """D3: put_back == search_order[0] is an identity for the neighbour family."""
    for _ in range(200):
        sample = {index: random.random() for index in range(random.randint(1, 8))}
        assert _argmax_distribution(sample) == _rank_source(sample)[0]
    print("B  _argmax_distribution(x) == _rank_distribution(x)[0]  PASS (200 random dicts)")
    print(f"   {'arm':<30}{'put_back == search_order[0]':>28}")
    for arm in ALL_ARMS:
        tokens, _, _ = run_arm(rollouts, arm, capture_distributions=False)
        same = sum(
            1
            for token in tokens
            if ">" in token
            and token.split("|", 1)[1].split(">")[0] == token.split("|", 1)[1].split(">")[1]
        )
        verdict = "identity" if same == len(tokens) else "two distinct quantities"
        print(f"   {arm:<30}{f'{same}/{len(tokens)}':>18}  {verdict}")


def section_c(rollouts) -> None:
    """D2: controlled ablation -- force the memory decision, hold everything else."""
    arm = "active_dreaming_matched"
    _, _, base = run_arm(rollouts, arm)
    _, _, escrow = run_arm(rollouts, arm, forced=neighbor.MemoryDecision.ESCROW)
    _, _, promote = run_arm(rollouts, arm, forced=neighbor.MemoryDecision.PROMOTE)
    print(f"C  controlled ablation on {arm} ({len(base)} steps, blend weight fixed at 0.28)")
    for label, left, right in (
        ("unmodified vs force-ESCROW", base, escrow),
        ("unmodified vs force-PROMOTE", base, promote),
        ("force-ESCROW vs force-PROMOTE", escrow, promote),
    ):
        distances = [total_variation(a, b) for a, b in zip(left, right, strict=True)]
        moved = sum(1 for a, b in zip(left, right, strict=True) if top1(a) != top1(b))
        print(
            f"   {label:<32} meanTV={statistics.fmean(distances):.6f}  "
            f"TV>1e-9: {sum(1 for d in distances if d > 1e-9):5d}/{len(distances)}  "
            f"argmax differs={moved}"
        )


def section_d(rollouts) -> None:
    """D2/D1: distribution-level disagreement vs what the Gate B token records."""
    runs = {arm: run_arm(rollouts, arm) for arm in NEIGHBOUR_ARMS}
    print(f"D  {len(next(iter(runs.values()))[0])} steps over {len(rollouts)} rollouts")
    print(f"   {'arm':<26}{'param':>7}   decisions")
    for arm in NEIGHBOUR_ARMS:
        counts = dict(collections.Counter(runs[arm][1]))
        print(f"   {arm:<26}{ARM_PARAMETERS[arm]!s:>7}   {counts}")
    print(
        f"\n   {'pair':<50}{'meanTV':>10}{'TV>1e-9':>9}{'argmax':>8}{'token':>7}"
        f"{'top-3':>9}{'top-4':>9}"
    )
    below = collections.Counter()
    for index, left in enumerate(NEIGHBOUR_ARMS):
        for right in NEIGHBOUR_ARMS[index + 1 :]:
            lt, _, ld = runs[left]
            rt, _, rd = runs[right]
            distances = [total_variation(a, b) for a, b in zip(ld, rd, strict=True)]
            rates = {}
            for name, fn in (("top1", top1), ("top3", top3), ("top4", top4_2dp)):
                rates[name] = sum(1 for a, b in zip(ld, rd, strict=True) if fn(a) != fn(b)) / len(
                    ld
                )
                if rates[name] < B2_THRESHOLD:
                    below[name] += 1
            token_diff = sum(1 for a, b in zip(lt, rt, strict=True) if a != b)
            print(
                f"   {left[:23] + ' / ' + right[:23]:<50}"
                f"{statistics.fmean(distances):>10.6f}"
                f"{sum(1 for d in distances if d > 1e-9):>9}"
                f"{int(rates['top1'] * len(ld)):>8}{token_diff:>7}"
                f"{rates['top3']:>9.4f}{rates['top4']:>9.4f}"
            )
    pairs = len(NEIGHBOUR_ARMS) * (len(NEIGHBOUR_ARMS) - 1) // 2
    print(
        f"\n   pairs under the b2 threshold ({B2_THRESHOLD}):  "
        f"top-1={below['top1']}/{pairs}   top-3={below['top3']}/{pairs}   "
        f"top-4@2dp={below['top4']}/{pairs}"
    )


def section_e(rollouts, arms: tuple[str, ...]) -> None:
    """D1: do the b1 pair ever make different memory decisions?"""
    runs = {arm: run_arm(rollouts, arm, capture_distributions=False) for arm in arms}
    for arm in arms:
        print(f"E  {arm:<26}{dict(collections.Counter(runs[arm][1]))}")
    if len(arms) == 2:
        left, right = (runs[arm] for arm in arms)
        decisions = sum(1 for a, b in zip(left[1], right[1], strict=True) if a != b)
        tokens = sum(1 for a, b in zip(left[0], right[0], strict=True) if a != b)
        print(
            f"E  decisions differ: {decisions} / {len(left[1])}     "
            f"tokens differ: {tokens} / {len(left[0])}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sections", default="A,B,C,D")
    parser.add_argument(
        "--rollouts", type=int, default=6, help="how many of the 72 scored rollouts to use for A-D"
    )
    parser.add_argument("--slice", default=None, help="LO:HI rollout range for section E")
    parser.add_argument("--arms", default="active_dreaming_matched,brainctl_matched")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    random.seed(args.seed)
    _install_probes()
    every = build_rollouts()
    sections = {item.strip().upper() for item in args.sections.split(",") if item.strip()}
    subset = every[: args.rollouts]
    if "A" in sections:
        section_a(subset)
    if "B" in sections:
        section_b(subset[:1])
    if "C" in sections:
        section_c(subset)
    if "D" in sections:
        section_d(subset)
    if "E" in sections:
        low, high = (int(x) for x in (args.slice or f"0:{args.rollouts}").split(":"))
        section_e(every[low:high], tuple(args.arms.split(",")))


if __name__ == "__main__":
    main()
