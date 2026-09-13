"""Collect numerical operator controls without replacing the production runtime."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from structure_two_backbone_wiring_probe import (  # noqa: E402
    BackboneWiringProbe,
    CIAVOutcomeKind,
)

from cpswm.system.continual.project_one_regime_loop import (  # noqa: E402
    PrototypeLoopConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (  # noqa: E402
    selected_v0_6_action_readout,
)
from cpswm.world_model.habits_transitions import (  # noqa: E402
    CauseSignalFrame,
    ChangeCause,
)
from cpswm.world_model.habits_transitions.joint_cause_bocpd import (  # noqa: E402
    JointCauseFactorizedBOCPD,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_aggregate() -> str:
    files = {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted((ROOT / "src").rglob("*.py"))
    }
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def top(distribution: dict[UUID, float]) -> str:
    return str(min(distribution, key=lambda key: (-distribution[key], str(key))))


def clean_distribution(distribution: dict[UUID, float]) -> dict[str, float]:
    return {str(key): value for key, value in distribution.items()}


def tv(left: dict[UUID, float], right: dict[UUID, float]) -> float:
    return 0.5 * math.fsum(abs(left[key] - right[key]) for key in left)


def legacy(days: int, *, loop_config: PrototypeLoopConfig | None = None):
    probe = BackboneWiringProbe.build(seed=7, loop_config=loop_config)
    last = None
    for observation in probe.observed_days()[:days]:
        last = probe.system.core.process_transition(probe.transition_for(observation))
    assert last is not None
    return probe, last


def cf_metrics() -> dict[str, object]:
    calm = {
        ChangeCause.OBSERVATION: 0.02,
        ChangeCause.ACTOR: 0.02,
        ChangeCause.HABIT: 0.02,
        ChangeCause.NOISE: 0.02,
    }
    shift = dict(calm)
    shift[ChangeCause.HABIT] = 0.95
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    def execute(signals: list[dict[ChangeCause, float]]):
        operator = JointCauseFactorizedBOCPD(hazard_probability=0.05)
        snapshot = None
        for index, signal in enumerate(signals):
            snapshot = operator.observe_online(
                CauseSignalFrame(timestamp=start + timedelta(days=index), signals=signal)
            )
        assert snapshot is not None
        return snapshot

    steady = execute([calm] * 6)
    changed = execute([calm] * 3 + [shift] * 3)
    return {
        "scope": (
            "real production CF-BOCPD class isolated input intervention; the separate "
            "wiring test proves its output is the runtime snapshot later read by CIAV"
        ),
        "legal_control": {
            "signals": "six identical calm frames",
            "segment_change_probability": steady.segment_change_probability,
            "habit_cause_probability": steady.segment_cause_posterior[ChangeCause.HABIT],
        },
        "public_input_intervention": {
            "signals": "three calm then three habit=0.95 frames",
            "segment_change_probability": changed.segment_change_probability,
            "habit_cause_probability": changed.segment_cause_posterior[ChangeCause.HABIT],
        },
        "change_probability_delta": (
            changed.segment_change_probability - steady.segment_change_probability
        ),
        "habit_probability_delta": (
            changed.segment_cause_posterior[ChangeCause.HABIT]
            - steady.segment_cause_posterior[ChangeCause.HABIT]
        ),
        "action_effect": "not isolated by this implementation-level intervention",
    }


def ccrr_metrics() -> dict[str, object]:
    narrow, _ = legacy(18, loop_config=PrototypeLoopConfig(confirmation_window=2))
    wide, _ = legacy(18, loop_config=PrototypeLoopConfig(confirmation_window=3))
    n_core, w_core = narrow.system.core, wide.system.core
    n_action, w_action = narrow.action_distribution(), wide.action_distribution()
    alpha_deltas = {
        str(location): n_core.hybrid_alpha(location) - w_core.hybrid_alpha(location)
        for location in narrow.case.locations
    }
    return {
        "scope": (
            "same public default history; only the declared CCRR confirmation window differs"
        ),
        "legal_control": (
            "the causal-matrix test repeats window=3 and requires identical classification"
        ),
        "window_2": {
            "committed": len(n_core._committed_events),
            "quarantined": len(n_core._quarantined_events),
            "action": clean_distribution(n_action),
            "top1": top(n_action),
        },
        "window_3": {
            "committed": len(w_core._committed_events),
            "quarantined": len(w_core._quarantined_events),
            "action": clean_distribution(w_action),
            "top1": top(w_action),
        },
        "action_tv": tv(n_action, w_action),
        "top1_changed": top(n_action) != top(w_action),
        "hybrid_alpha_window2_minus_window3": alpha_deltas,
        "max_hybrid_alpha_absolute_delta": max(abs(value) for value in alpha_deltas.values()),
    }


def rgrc_metrics() -> dict[str, object]:
    rows: dict[str, object] = {}
    distributions: dict[str, dict[UUID, float]] = {}
    for label, outcome in (
        ("legal_negative_no_closure", CIAVOutcomeKind.NOT_DETECTED),
        ("public_different_location_feedback", CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION),
    ):
        probe = BackboneWiringProbe.build(seed=7)
        transition = probe.transition_for(probe.observed_days()[0])
        result, _ = probe.run_direct_p5(
            transition, ciav_input=probe.ciav_input(transition, outcome=outcome)
        )
        core = probe.system.core
        distributions[label] = probe.action_distribution()
        rows[label] = {
            "committed": len(core._committed_events),
            "quarantined": len(core._quarantined_events),
            "ledger_entries": len(core._hybrid_loop.ledger.export_state().entries),
            "hybrid_alpha": {
                str(location): core.hybrid_alpha(location) for location in probe.case.locations
            },
            "action": clean_distribution(distributions[label]),
            "top1": top(distributions[label]),
            "feedback_closure": result.feedback_result is not None,
        }
    left = distributions["legal_negative_no_closure"]
    right = distributions["public_different_location_feedback"]
    return {
        "scope": (
            "same public transition; CIAV realized outcome controls whether feedback reaches RGRC"
        ),
        "runs": rows,
        "action_tv": tv(left, right),
        "top1_changed": top(left) != top(right),
        "ordinary_information_delta_note": (
            "continuous raw trace checks ΔΛ/Δξ; it remains identically zero"
        ),
    }


def ciav_metrics() -> dict[str, object]:
    rows: dict[str, object] = {}
    distributions: dict[str, dict[UUID, float]] = {}
    cases = (
        ("negative_control", None),
        ("same_location_owner_0_95", 0.95),
        ("same_location_owner_0_05", 0.05),
    )
    for label, owner_likelihood in cases:
        probe = BackboneWiringProbe.build(
            seed=7, action_readout=selected_v0_6_action_readout()
        )
        days = probe.observed_days()
        for observation in days[:4]:
            transition = probe.transition_for(observation)
            probe.run_direct_p5(
                transition,
                ciav_input=probe.ciav_input(
                    transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
                ),
            )
        transition = probe.transition_for(days[4])
        ciav = (
            probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED)
            if owner_likelihood is None
            else probe.ciav_input(
                transition,
                outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION,
                owner_likelihood=owner_likelihood,
            )
        )
        result, _ = probe.run_direct_p5(transition, ciav_input=ciav)
        distributions[label] = probe.action_distribution()
        rows[label] = {
            "action": clean_distribution(distributions[label]),
            "top1": top(distributions[label]),
            "ciav_executed": result.ciav_receipt is not None,
            "fast_verification_changed": (
                None
                if result.fast_verification_receipt is None
                else result.fast_verification_receipt.changed
            ),
        }
    control = distributions["negative_control"]
    return {
        "scope": "public CIAV input and real executor; no manual prepared state",
        "runs": rows,
        "owner_0_95_vs_control_tv": tv(
            distributions["same_location_owner_0_95"], control
        ),
        "owner_0_05_vs_control_tv": tv(
            distributions["same_location_owner_0_05"], control
        ),
        "owner_0_95_top1_changed": (
            top(distributions["same_location_owner_0_95"]) != top(control)
        ),
        "owner_0_05_top1_changed": (
            top(distributions["same_location_owner_0_05"]) != top(control)
        ),
    }


def main() -> int:
    started = time.time()
    before = source_aggregate()
    result = {
        "classification": "engineering causal metrics; not ablation or scientific acceptance",
        "command": [str(Path(sys.executable).resolve()), str(Path(__file__).resolve())],
        "cwd": str(ROOT),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "last_commit_touching_src": subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", "src"], cwd=ROOT, text=True
        ).strip(),
        "started_unix": started,
        "cf_bocpd": cf_metrics(),
        "ccrr": ccrr_metrics(),
        "rgrc": rgrc_metrics(),
        "ciav": ciav_metrics(),
        "source_before_aggregate_sha256": before,
        "source_after_aggregate_sha256": source_aggregate(),
        "elapsed_seconds": time.time() - started,
        "exit_code": 0,
    }
    result["source_unchanged"] = (
        result["source_before_aggregate_sha256"]
        == result["source_after_aggregate_sha256"]
    )
    (OUT / "operator_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "source_unchanged": result["source_unchanged"],
                "ccrr_action_tv": result["ccrr"]["action_tv"],
                "rgrc_action_tv": result["rgrc"]["action_tv"],
                "ciav_low_owner_action_tv": result["ciav"]["owner_0_05_vs_control_tv"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
