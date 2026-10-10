"""Post-hoc read-only comparison of existing readouts over identical production states."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
from pathlib import Path

from run_correction_replay_comparison import (
    CIAVOutcomeKind,
    GroundedTransition,
    build,
    raw_for,
    soft_memory_baseline,
    source_identity,
    summary,
)
from run_matched_transition_death_test import digest, load, save

from cpswm.system.evaluation_operations.structure_two_action_death_test import (
    StructureTwoActionScenarioGenerator,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    selected_v0_6_action_readout,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256


def run(output, reference_root):
    output.mkdir(parents=True, exist_ok=False)
    _, files = source_identity()
    root = Path(__file__).resolve().parents[1]
    for name in ("tools/diagnose_core_readout.py", "tools/run_correction_replay_comparison.py"):
        files[name] = digest(root / name)
    source = content_sha256(files)
    cases = []
    for mode in (
        CIAVOutcomeKind.DETECTED_SAME_LOCATION,
        CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION,
    ):
        for seed in (7, 8, 9):
            ciav = {}
            probe, producer, stream, store, _ = build(
                output / f"{mode}-{seed}.db",
                seed=seed,
                source=source,
                ciav_journal=ciav,
                ciav_outcome=mode,
            )
            rows = []
            for index, day in enumerate(probe.observed_days()[:12]):
                transition = probe.transition_for(day)
                when = transition.after.detection_time + timedelta(minutes=1)
                ids = stream.admit((raw_for(transition, index),), received_at=when)
                producer.output = GroundedTransition(
                    transition, ids, "CONTROLLED_ORACLE_V1", "ASSUMED_NOT_EMPIRICAL"
                )
                receipt = stream.advance(cutoff=when)
                core = stream._system.core
                before = summary(stream)
                readouts = {}
                for name, config in (
                    ("default", ActionReadoutConfig()),
                    ("latest_owner", ActionReadoutConfig(readout=ActionReadout.LATEST_OWNER_EVENT)),
                    ("previously_selected_v0_6", selected_v0_6_action_readout()),
                ):
                    dist = core.action_location_distribution(core.current_snapshot, readout=config)
                    readouts[name] = {
                        "distribution": {str(k): v for k, v in dist.items()},
                        "choice": str(max(sorted(dist, key=str), key=dist.__getitem__)),
                    }
                readouts["soft_memory"] = soft_memory_baseline(
                    probe, tuple(core._observed_events.items())
                )
                readouts["soft_memory"]["choice"] = readouts["soft_memory"]["argmax"]
                # Also give ordinary counts the *current* CIAV-revised actor
                # masses, not only the earlier event.evidence actor posterior.
                counts = dict.fromkeys(probe.case.locations, 1.0)
                actor_events = []
                for event in core._fast_action_events.values():
                    counts[event.location_id] += event.owner_mass
                    actor_events.append(
                        {
                            "time": event.evidence.event_time.isoformat(),
                            "location": str(event.location_id),
                            "current_owner_mass": event.owner_mass,
                            "original_owner_mass": event.evidence.actor_posterior[
                                probe.case.owner_actor
                            ],
                        }
                    )
                total = sum(counts.values())
                readouts["soft_current_actor"] = {
                    "distribution": {str(k): v / total for k, v in counts.items()},
                    "choice": str(max(sorted(counts, key=str), key=counts.__getitem__)),
                }
                if summary(stream) != before:
                    raise RuntimeError("post-hoc readout mutated production state")
                rows.append(
                    {
                        "day": day.day,
                        "readouts": readouts,
                        "committed": len(core._committed_events),
                        "fast_events": len(core._fast_action_events),
                        "observed": len(core._observed_events),
                        "current_actor_events": actor_events,
                        "primary_conclusion": str(
                            receipt.result.primary_result.decision.conclusion
                        ),
                        "primary_rationale": receipt.result.primary_result.decision.rationale,
                        "quarantine_reasons": dict(
                            Counter(
                                str(x.quarantine_reason) for x in core._write_eligibility.values()
                            )
                        ),
                    }
                )
            # Independent truth opened after the entire runtime rollout has completed.
            case = StructureTwoActionScenarioGenerator(
                duration_days=32, observation_coverage=1.0
            ).generate(seed)
            if content_sha256(probe.case) != content_sha256(case.visible):
                raise ValueError("case binding differs")
            reference_path = (
                reference_root / f"cpswm-paired-v3-{mode}-{seed}-20261010/comparison.json"
            )
            reference = load(reference_path)
            for row, ref in zip(rows, reference["steps"], strict=True):
                if row["readouts"]["default"]["distribution"] != ref["state"]["distribution"]:
                    raise ValueError("fresh default readout differs from frozen correction prefix")
                row["true_habit_location"] = str(
                    case.truth_by_day[row["day"]].true_owner_habit_location
                )
                row["correct"] = {
                    name: value["choice"] == row["true_habit_location"]
                    for name, value in row["readouts"].items()
                }
            cases.append(
                {
                    "mode": str(mode),
                    "seed": seed,
                    "rows": rows,
                    "reference_sha256": digest(reference_path),
                    "visible_case_sha256": content_sha256(probe.case),
                    "default_prefix_equal_reference": True,
                    "readouts_do_not_mutate_state": True,
                    "correct": {
                        name: sum(r["correct"][name] for r in rows) for name in rows[0]["readouts"]
                    },
                }
            )
            store.close()
            print(mode, seed, cases[-1]["correct"], flush=True)
    result = {
        "source_sha256": source,
        "source_files": files,
        "cases": cases,
        "config": {
            "default": ActionReadoutConfig().__dict__
            if hasattr(ActionReadoutConfig(), "__dict__")
            else str(ActionReadoutConfig()),
            "previously_selected_v0_6": str(selected_v0_6_action_readout()),
        },
        "scope": (
            "Post-hoc development readout diagnosis using existing config, no retuning, "
            "no policy change, no physical actions. Latest-owner and soft memory are "
            "controls; ties do not establish novel mechanism value."
        ),
    }
    result["source_unchanged"] = all(digest(root / name) == value for name, value in files.items())
    if not result["source_unchanged"]:
        raise RuntimeError("source changed")
    save(output / "readout-diagnosis.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reference-root", type=Path, required=True)
    a = p.parse_args()
    run(a.output, a.reference_root)
