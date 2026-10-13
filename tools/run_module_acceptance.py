"""One source-bound module acceptance entry; explicit gaps prevent full acceptance.

Run with the checkout's .venv interpreter. Exit 0 is reserved for full acceptance;
currently successful bounded checks exit 2 (PARTIAL), execution/check failures 1.
No old run is reused and no natural/robot capability is inferred from D0 tests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATORS = {"opceu", "pchmp", "cf_bocpd", "ccrr", "rgrc", "ciav", "orrer_cheh"}
GAPS = {
    "natural_semantic_bridge": "BLOCKED: natural instance/actor/role event bridge absent",
    "natural_person_likelihood": "NOT_VALIDATED: no natural person calibration in this suite",
    "glass_surface_geometry": "BLOCKED: rejection of background depth is not surface recovery",
    "global_source_retraction": "NOT_VALIDATED: only native location-source transaction exercised",
    "default_sampling_migration": "BLOCKED: default runtime retains systematic sampling",
    "physical_robot_loop": "NOT_VALIDATED: D0 search is not navigation/grasp/place execution",
    "independent_B_S1_full_suite": "NOT_VALIDATED: local bounded checks only",
    "joint_scientific_gain": "NOT_ESTABLISHED: engineering checks do not prove action benefit",
}
TEST_GROUPS = {
    "visual_actor_boundaries": [
        "test_grounding_readout_feedback_repair",
        "test_natural_vision",
        "test_natural_mask_surface",
    ],
    "production_wiring": [
        "test_structure_two_production_system",
        "test_structure_two_backbone_operator_wiring",
    ],
    "current_event_inference": [
        "test_particle_support_sampling",
        "test_current_event",
        "test_current_event_adversarial",
        "test_current_event_task_receipt",
        "test_shared_location",
        "test_current_location",
        "test_executed_search",
        "test_active_location_search",
        "test_task_readout_repair",
        "test_full_mechanism_value_diagnostic",
        "test_structure_two_stateful_full_joint",
        "test_structure_two_stateful_full_joint_adversarial",
        "test_structure_two_w3_native_posterior_projection",
    ],
    "acceptance_integrity": ["test_module_acceptance"],
}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root=ROOT):
    paths = [root / n for n in ("pyproject.toml", "uv.lock")]
    for folder in (
        "src",
        "tools",
        "tests",
        "configs",
        "artifacts/project_two_v04_development",
        "apps/evaluation_runner",
    ):
        paths.extend(
            p
            for p in (root / folder).rglob("*")
            if p.is_file()
            and p.suffix in (".py", ".json", ".toml", ".yaml", ".yml")
            and "__pycache__" not in p.parts
        )
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def pytest_result(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    if not cases:
        raise ValueError("No executed test cases")
    result = dict(tests=len(cases), failures=0, errors=0, skipped=0)
    for case in cases:
        for tag, key in [("failure", "failures"), ("error", "errors"), ("skipped", "skipped")]:
            result[key] += case.find(tag) is not None
    result["passed"] = result["tests"] - sum(result[k] for k in ("failures", "errors", "skipped"))
    return result


def classify(stages, unchanged):
    if not unchanged or not stages or any(s["status"] == "FAILED" for s in stages):
        return "FAILED", 1
    if any(s["status"] != "PASSED" for s in stages) or GAPS:
        return "PARTIAL", 2
    return "PASSED", 0


def environment():
    expected = ROOT / ".venv"
    if Path(sys.prefix).resolve() != expected.resolve() or not (expected / "pyvenv.cfg").is_file():
        raise ValueError(
            "Use this checkout .venv; missing pyvenv.cfg/base-interpreter fallback refused"
        )
    modules = {}
    for name in (
        "cpswm",
        "cpswm.system.prototype_spine",
        "cpswm.system.structure_two_production_system",
        "cpswm.system.evaluation_operations.structure_two_current_event",
        "cpswm.perception_mapping.natural_vision",
    ):
        m = importlib.import_module(name)
        path = Path(m.__file__).resolve()
        if not path.is_relative_to(ROOT / "src"):
            raise ValueError("Foreign checkout import: " + str(path))
        modules[name] = str(path.relative_to(ROOT))
    return dict(
        python=sys.version,
        executable=sys.executable,
        prefix=sys.prefix,
        modules=modules,
        packages={
            p: importlib.metadata.version(p)
            for p in ("pytest", "numpy", "pydantic", "cryptography", "torch", "torchvision")
        },
        venv_config_sha256=sha(expected / "pyvenv.cfg"),
        lock_sha256=sha(ROOT / "uv.lock"),
    )


def native_run(output):
    from run_current_event import dataset_for, evaluate, plain
    from run_particle_support import CONFIGS

    from cpswm.contracts import ProjectTwoDatasetSplit

    dataset = dataset_for("sparse32", [67001])
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    assert len(episode.steps) == 32
    save(output / "visible.json", episode.model_dump(mode="json"))
    save(output / "truth.json", dataset.truth_for(episode.episode_id).model_dump(mode="json"))
    for label, config in CONFIGS.items():
        result = plain(evaluate(dataset, episode, **config))
        save(output / (label + ".json"), result)
        print(label, len(result["actions"]), "fresh steps", flush=True)
    return dict(
        runs=4,
        steps=128,
        condition="sparse32",
        split="validation",
        seed=7,
        scope="fixed development engineering replay, not fresh scientific holdout",
    )


def audit_native(output):
    from analyze_joint_action_gap import reconstruct, stats, tv
    from run_particle_support import CONFIGS
    from score_current_event import verify_run
    from score_particle_support import verify_sampling

    raw = output.parents[1] / "native_run" / "data"
    visible, truth = read(raw / "visible.json"), read(raw / "truth.json")
    runs, summaries = {}, {}
    for label in CONFIGS:
        r = read(raw / (label + ".json"))
        assert r["sampling_method"] == "independent_strata_v1" and r["profile"] == "v06"
        assert r["arm"] == CONFIGS[label]["arm"]
        assert r["consume_new"] == CONFIGS[label]["consume_new"]
        verify_run(r, visible, truth)
        sampling = verify_sampling(r)
        rows = reconstruct(r, truth)
        receipts = r["native_audit"]["operator_flow_receipts"]
        executed = Counter(x["operator"] for x in receipts if x["executed"])
        changed = Counter(x["operator"] for x in receipts if x["changed_state"])
        assert set(executed) == OPERATORS
        summaries[label] = dict(
            steps=len(rows),
            put_errors=r["put_errors"],
            checks=sum(x["search"]["paid_checks"] for x in r["actions"]),
            executed_operators=dict(executed),
            changed_operators=dict(changed),
            sampling=dict(sampling),
            ess=stats([x["ess"] for x in rows]),
            ess_below_two=sum(x["ess"] < 2 for x in rows),
            rb_hashes_verified=24 * len(rows),
            readout_max_error=max(x["readout_error"] for x in rows),
        )
        runs[label] = r
    j, f = runs["joint"], runs["matched_factor"]
    for a, b, na, nb in zip(
        j["actions"], f["actions"], j["native_evidence"], f["native_evidence"], strict=True
    ):
        assert a["search"] == b["search"]
        assert na["observation"] == nb["observation"]
        assert na["fairness"]["particle_budget"] == nb["fairness"]["particle_budget"] == 24
    return dict(
        arms=summaries,
        paired_steps=32,
        distinct_put_actions=sum(
            a["put_back"] != b["put_back"] for a, b in zip(j["actions"], f["actions"], strict=True)
        ),
        distinct_distributions=sum(
            tv(a["after"], b["after"]) > 1e-10
            for a, b in zip(j["actions"], f["actions"], strict=True)
        ),
        scientific_status="DESCRIPTIVE_DEVELOPMENT_ONLY",
    )


def worker(name, output):
    if name == "environment":
        return environment()
    if name == "native_run":
        return native_run(output)
    if name == "native_audit":
        return audit_native(output)
    if name == "revision_continuation":
        from probe_current_event import probe
        from run_current_event import plain

        return plain(probe())
    if name == "default_sampling":
        from run_current_event import build, dataset_for

        from cpswm.contracts import ProjectTwoDatasetSplit
        from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
            StatefulFullJointRuntime,
        )

        data = dataset_for("sparse32", [67001])
        ep = data.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
        current = build(data, ep, "stateful_full_joint").runtime
        legacy = StatefulFullJointRuntime(
            arm=current.arm, config=current.config, neural_model=current.neural_model
        )
        q, seed = [1 / 72] * 72, hashlib.sha256(b"enumerated-support:0").hexdigest()
        old, new = (
            legacy._proposal_draw_indices(q, 24, seed),
            current._proposal_draw_indices(q, 24, seed),
        )
        assert old == legacy._systematic_draw_indices(q, 24, seed)
        assert len(set(i % 3 for i in old)) == 1 and len(set(i % 3 for i in new)) == 3
        return dict(
            default_method="systematic",
            development_method=current.sampling_method,
            legacy_distinct_child_types=len(set(i % 3 for i in old)),
            development_distinct_child_types=len(set(i % 3 for i in new)),
            migration_status="NOT_MIGRATED",
            scope="enumerated proposal behavior, not full default application acceptance",
        )
    raise ValueError(name)


def run_stage(output, name, args, env, timeout, junit=False):
    folder = output / name
    folder.mkdir()
    command = [sys.executable, *args]
    if junit:
        command += ["--junitxml=" + str(folder / "tests.xml")]
    record = dict(name=name, command=command, started_unix=time.time(), status="RUNNING")
    save(folder / "started.json", record)
    print(name, "started", flush=True)
    with (folder / "stdout.log").open("w") as out, (folder / "stderr.log").open("w") as err:
        proc = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=out, stderr=err, start_new_session=True
        )
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code = 124
    record.update(
        exit_code=code,
        seconds=time.time() - record["started_unix"],
        status="PASSED" if code == 0 else "FAILED",
    )
    if junit:
        try:
            record["tests"] = pytest_result(folder / "tests.xml")
            if record["tests"]["failures"] or record["tests"]["errors"]:
                record["status"] = "FAILED"
            elif record["tests"]["skipped"] and code == 0:
                record["status"] = "PARTIAL"
        except (OSError, ET.ParseError, ValueError) as error:
            record.update(status="FAILED", validation_error=str(error))
    elif code == 0:
        try:
            record["result_sha256"] = sha(folder / "data" / "result.json")
        except OSError as error:
            record.update(status="FAILED", validation_error=str(error))
    record["stdout_sha256"], record["stderr_sha256"] = (
        sha(folder / "stdout.log"),
        sha(folder / "stderr.log"),
    )
    save(folder / "result.json", record)
    print(name, record["status"], flush=True)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--worker",
        choices=[
            "environment",
            "native_run",
            "native_audit",
            "revision_continuation",
            "default_sampling",
        ],
    )
    p.add_argument("--stage-timeout", type=int, default=1200)
    args = p.parse_args()
    if args.worker:
        save(args.output / "result.json", worker(args.worker, args.output))
        return 0
    if args.stage_timeout <= 0:
        p.error("stage-timeout must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    save(
        output / "source.json",
        dict(
            head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            files=before,
        ),
    )
    env = os.environ.copy()
    env.update(
        PYTHONPATH=os.pathsep.join(str(ROOT / x) for x in ("src", "tools", "tests")),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    stages = []

    def launch(name, command, junit=False):
        stages.append(run_stage(output, name, command, env, args.stage_timeout, junit))

    def launch_worker(name):
        launch(
            name,
            [
                str(Path(__file__).resolve()),
                "--worker",
                name,
                "--output",
                str(output / name / "data"),
            ],
        )

    launch_worker("environment")
    if stages[-1]["status"] == "PASSED":
        launch_worker("default_sampling")
        for name, names in TEST_GROUPS.items():
            launch(
                name,
                ["-m", "pytest", "-o", "addopts=", "-q", *[f"tests/{n}.py" for n in names]],
                True,
            )
        launch_worker("native_run")
        if stages[-1]["status"] == "PASSED":
            launch_worker("native_audit")
        launch_worker("revision_continuation")
    after = snapshot()
    status, code = classify(stages, before == after)
    save(
        output / "summary.json",
        dict(
            status=status,
            exit_code=code,
            source_unchanged=before == after,
            changed_sources=sorted(
                k for k in before.keys() | after.keys() if before.get(k) != after.get(k)
            ),
            stages=stages,
            gaps=GAPS,
            scope="bounded module execution, not full unified/S1/robot acceptance",
        ),
    )
    artifacts = {
        str(x.relative_to(output)): sha(x) for x in sorted(output.rglob("*")) if x.is_file()
    }
    save(output / "MANIFEST.json", artifacts)
    print(status, "exit", code, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
