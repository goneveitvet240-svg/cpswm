"""Predeclared S1 viewpoint matrix; failures retain their original task slots.

No model fitting, metric changes, or runtime access to evaluator target IDs.
Live paired groups are serial; each owns one frozen Unity process.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = (25, 30, 35)
QUERIES = ("bottle:0", "bottle:1", "bowl:0")
ARMS = ("fixed", "active", "no-update", "memory-retain", "memory-reset")


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def sources():
    return {
        str(p.relative_to(ROOT)): sha(p)
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }


def invoke(args, log, env, records):
    start = time.monotonic()
    record = dict(
        command=[str(a) for a in args], log=str(log), started=datetime.now(UTC).isoformat()
    )
    records.append(record)
    with log.open("x") as output:
        result = subprocess.run(record["command"], cwd=ROOT, env=env, stdout=output, stderr=output)
    record.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - start)
    return result.returncode


def main(a):
    a.output.mkdir(parents=True, exist_ok=False)
    pins = sources()
    externals = {
        name: dict(path=str(getattr(a, name).resolve()), sha256=sha(getattr(a, name)))
        for name in ("weights", "mask_weights", "house", "model", "targets", "binary")
    }
    matrix = [
        dict(
            id=f"view-{view}-{kind}",
            degrees=[view, 5, 5],
            arms=list(ARMS[3:] if kind == "memory" else ARMS[:3]),
            memory_only=kind == "memory",
        )
        for view in VIEWS
        for kind in ("policy", "memory")
    ]
    plan = dict(
        schema="cpswm-system-s1@1",
        created=datetime.now(UTC).isoformat(),
        code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        production_baseline="745613ef0b804b5da4d1d2afcbba56fd9f78925c",
        sources=pins,
        externals=externals,
        python=sys.version,
        dependencies={
            name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "numpy", "pydantic", "opencv-contrib-python")
        },
        matrix=matrix,
        queries=QUERIES,
        planned_episodes=15,
        planned_query_slots=45,
        budget_per_episode=3,
        later_task_budget=1,
        scope="one development house, three correlated viewpoints, controlled semantic bootstrap",
        independence="no independent scene replication or B acceptance",
        missing=(
            "preserve unexecuted/failed slots; report completed denominator and planned denominator"
        ),
        retry="no automatic retries or adaptive replacement of failed views/targets",
    )
    save(a.output / "plan.json", plan)
    env = dict(os.environ, PYTHONPATH="src:tests:tools")
    env.update(CPSWM_SSDLITE_WEIGHTS=str(a.weights), CPSWM_MASK_WEIGHTS=str(a.mask_weights))
    commands, groups = [], []
    save(a.output / "progress.json", dict(status="RUNNING", groups=groups, commands=commands))
    for cell in matrix:
        if sources() != pins:
            raise RuntimeError("frozen source changed during matrix; do not mix results")
        for spec in externals.values():
            if sha(Path(spec["path"])) != spec["sha256"]:
                raise RuntimeError("frozen input changed during matrix")
        folder = a.output / cell["id"]
        args = [sys.executable, "tools/run_surface_comparison.py", "--output", folder]
        for name in ("weights", "mask_weights", "sdk_python", "binary", "house", "model"):
            args += ["--" + name.replace("_", "-"), getattr(a, name)]
        args += ["--degrees", *map(str, cell["degrees"]), "--target", *QUERIES]
        if cell["memory_only"]:
            args.append("--memory-only")
        print(json.dumps(dict(starting=cell["id"], expected_arms=cell["arms"])), flush=True)
        code = invoke(args, a.output / (cell["id"] + ".log"), env, commands)
        group = dict(id=cell["id"], runtime_returncode=code, arms=[], pair_status="INCOMPLETE")
        for arm in cell["arms"]:
            run = folder / arm
            result = read(run / "result.json") if (run / "result.json").exists() else {}
            entry = dict(
                arm=arm,
                runtime_status=result.get("status", "NOT_EXECUTED"),
                physical_dispatches=result.get("physical_dispatches"),
                planned_query_slots=len(QUERIES),
                evaluated_query_slots=0,
                reported_statuses=[r["status"] for r in result.get("final_reports", [])],
            )
            if result.get("status") == "COMPLETED" and (run / "transport/evaluator_only").exists():
                evaluation = run / "evaluation.json"
                scored = invoke(
                    [
                        sys.executable,
                        "tools/evaluate_surface_episode.py",
                        run,
                        a.targets,
                        evaluation,
                    ],
                    a.output / (cell["id"] + "-" + arm + "-evaluation.log"),
                    env,
                    commands,
                )
                entry["evaluation_returncode"] = scored
                if scored == 0:
                    value = read(evaluation)
                    entry.update(
                        evaluated_query_slots=value["task_count"],
                        identity_correct=value["identity_correct"],
                        position_correct=value["position_correct"],
                        joint_success=value["joint_success"],
                    )
            # Fresh processes check persisted reports without replaying bootstrap.
            if result.get("status") == "COMPLETED":
                entry["restore_returncode"] = invoke(
                    [sys.executable, "tools/run_surface_episode.py", "restore", "--output", run],
                    a.output / (cell["id"] + "-" + arm + "-restore.log"),
                    env,
                    commands,
                )
            group["arms"].append(entry)
        if all(e["evaluated_query_slots"] == len(QUERIES) for e in group["arms"]):
            summary = folder / "comparison.json"
            group["comparison_returncode"] = invoke(
                [sys.executable, "tools/summarize_surface_comparison.py", folder, summary],
                a.output / (cell["id"] + "-comparison.log"),
                env,
                commands,
            )
            if group["comparison_returncode"] == 0:
                group["pair_status"] = read(summary)["status"]
        groups.append(group)
        save(a.output / "progress.json", dict(status="RUNNING", groups=groups, commands=commands))
        print(json.dumps(dict(completed_group=group)), flush=True)
    totals = {}
    for arm in ARMS:
        entries = [e for g in groups for e in g["arms"] if e["arm"] == arm]
        totals[arm] = dict(
            planned_episodes=3,
            completed_episodes=sum(e["runtime_status"] == "COMPLETED" for e in entries),
            planned_query_slots=9,
            evaluated_query_slots=sum(e["evaluated_query_slots"] for e in entries),
            identity_correct=sum(e.get("identity_correct", 0) for e in entries),
            position_correct=sum(e.get("position_correct", 0) for e in entries),
            confirmed_joint_success=sum(e.get("joint_success", 0) for e in entries),
            known_physical_dispatches=sum(e["physical_dispatches"] or 0 for e in entries),
            unaccounted_episode_dispatches=sum(e["physical_dispatches"] is None for e in entries),
            successful_fresh_restores=sum(e.get("restore_returncode") == 0 for e in entries),
        )
    unchanged = sources() == pins
    complete = (
        unchanged
        and all(g["pair_status"] == "VALID_DEVELOPMENT_PAIR" for g in groups)
        and all(t["successful_fresh_restores"] == 3 for t in totals.values())
    )
    summary = dict(
        status="COMPLETE_DEVELOPMENT_MATRIX" if complete else "PARTIAL_OR_FAILED_MATRIX",
        sources_unchanged=unchanged,
        groups=groups,
        totals=totals,
        commands=commands,
        scope=plan["scope"],
        independence=plan["independence"],
        statistics="descriptive counts only; shared query actions counted once per episode",
    )
    save(a.output / "summary.json", summary)
    save(a.output / "progress.json", summary)
    print(json.dumps(dict(status=summary["status"], totals=totals)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "output",
        "weights",
        "mask-weights",
        "sdk-python",
        "binary",
        "house",
        "model",
        "targets",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    main(parser.parse_args())
