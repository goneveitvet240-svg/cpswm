"""Source-equivalent full/suffix replay cost probe; run each method in a fresh process."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.memory import SimulationMemory
from cpswm.simulation.suffix_memory import SuffixReplayMemory, runtime_digest
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def archived_inputs(arm):
    path = ROOT / "docs/reviews/pc_a/research_pilot_2026-10-23/evidence/e2.json"
    data = json.loads(path.read_text())
    for row in data["e2"]["rows"]:
        if row["arm"] != arm:
            continue
        observations = []
        for point in row["checkpoints"]:
            body = dict(point["input"])
            body["visibility"] = Visibility(body["visibility"])
            body["actors"] = tuple(tuple(x) for x in body["actors"])
            observations.append(Observation(**body))
        yield row["condition"] + ":" + row["trajectory"], observations


def long_inputs():
    # Explicit engineering stress input, not a heldout scientific world sample.
    episode = "suffix-development-long-24"
    observations = [
        Observation(
            episode,
            f"source:{i}",
            f"event:{i}",
            i,
            i,
            "target",
            Visibility.OBSERVED,
            ("left", "center", "right")[i % 3],
            (("owner", 0.7), ("guest", 0.3)),
            identity_probability=0.8,
        )
        for i in range(24)
    ]
    active = {o.event_id: o for o in observations}
    for tick, index in enumerate((22, 12, 22, 0, 12, 0), 30):
        original = observations[index]
        old = active[original.event_id]
        corrected = replace(
            original,
            source_id=f"revision:{tick}",
            revises=old.source_id,
            available_at=tick,
            actors=(("guest", 1.0),) if old.revises is None else original.actors,
        )
        observations.append(corrected)
        active[original.event_id] = corrected
    return [(episode, observations)]


def peak_rss_bytes():
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system() == "Darwin" else value * 1024


def run(implementation, arm, case, stride=4, bound=8):
    cases = list(archived_inputs(arm)) if case == "archive" else long_inputs()
    rows = []
    rss_before = peak_rss_bytes()
    wall_started = perf_counter()
    for name, inputs in cases:
        cls = SimulationMemory if implementation == "full" else SuffixReplayMemory
        kwargs = (
            {}
            if implementation == "full"
            else {
                "checkpoint_stride": stride,
                "max_checkpoints": bound,
            }
        )
        memory = cls(inputs[0].episode_id, ("left", "center", "right"), arm, ROOT, **kwargs)
        checkpoints = []
        for index, obs in enumerate(inputs):
            start = perf_counter()
            memory.ingest(obs, obs.available_at)
            seconds = perf_counter() - start
            checkpoints.append(
                {
                    "input": obs.payload(),
                    "input_sha256": content_sha256(obs),
                    "ingest_seconds": seconds,
                    "audit": memory.audit(),
                    "full_runtime_sha256": runtime_digest(memory.runtime),
                }
            )
            print(
                f"{implementation} {arm} {name} {index + 1}/{len(inputs)} "
                f"ingest={seconds:.3f}s scores={memory.native_target_scores}",
                flush=True,
            )
        rows.append({"case": name, "checkpoints": checkpoints})
    return {
        "implementation": implementation,
        "arm": arm,
        "case_set": case,
        "stride": stride if implementation != "full" else None,
        "max_checkpoints": bound if implementation != "full" else None,
        "rows": rows,
        "wall_seconds_including_diagnostics": perf_counter() - wall_started,
        "rss_before_bytes": rss_before,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "memory_metric_scope": "whole fresh process high-water mark; not isolated cache bytes",
    }


def compare_reports(full, suffix):
    if full["source_sha"] != suffix["source_sha"]:
        raise ValueError("different code sources")
    a, b = full["run"], suffix["run"]
    if (a["implementation"], b["implementation"]) != ("full", "suffix"):
        raise ValueError("expected full then suffix")
    if (a["arm"], a["case_set"]) != (b["arm"], b["case_set"]):
        raise ValueError("different experiment inputs")
    excluded = {
        "rebuilds",
        "total_native_target_scores",
        "replay_implementation",
        "checkpoint_stride",
        "max_checkpoints",
        "checkpoint_count",
        "last_replay",
    }
    times, scores = [0.0, 0.0], [0, 0]
    count = 0
    for x, y in zip(a["rows"], b["rows"], strict=True):
        if x["case"] != y["case"]:
            raise ValueError("case order differs")
        for px, py in zip(x["checkpoints"], y["checkpoints"], strict=True):
            if px["input"] != py["input"] or px["full_runtime_sha256"] != py["full_runtime_sha256"]:
                raise ValueError("source or full native state differs")
            ax = {k: v for k, v in px["audit"].items() if k not in excluded}
            ay = {k: v for k, v in py["audit"].items() if k not in excluded}
            if ax != ay:
                raise ValueError("memory/decision/ledger state differs")
            times[0] += px["ingest_seconds"]
            times[1] += py["ingest_seconds"]
            count += 1
        scores[0] += x["checkpoints"][-1]["audit"]["total_native_target_scores"]
        scores[1] += y["checkpoints"][-1]["audit"]["total_native_target_scores"]
    return {
        "matched_checkpoints": count,
        "full_scores": scores[0],
        "suffix_scores": scores[1],
        "full_ingest_seconds": times[0],
        "suffix_ingest_seconds": times[1],
        "measured_ingest_speedup": times[0] / times[1],
        "full_peak_rss_bytes": a["peak_process_rss_bytes"],
        "suffix_peak_rss_bytes": b["peak_process_rss_bytes"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=("full", "suffix"), required=True)
    parser.add_argument("--arm", choices=("native_joint", "native_factorized"), required=True)
    parser.add_argument("--case", choices=("archive", "long"), required=True)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--max-checkpoints", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "protocol": "suffix-replay-development-v1",
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "evidence_level": "engineering_equivalence_and_cost_not_scientific_advantage",
        "run": run(args.implementation, args.arm, args.case, args.stride, args.max_checkpoints),
    }
    report["content_sha256"] = content_sha256(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
