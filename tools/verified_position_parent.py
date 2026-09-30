"""Pinned development parent, with fixed historical full refit before loading.

This is archive verification, not independent data collection or native authority.
No command saved in a ledger is executed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from diagnose_offline_frontend import digest, inventory, require, source_identity

PATH_ARGUMENTS = (
    "controls_results",
    "controls_source",
    "affinity_results",
    "affinity_source",
    "historical_python",
    "collection",
    "capture_source",
    "archive",
    "sdk_python",
    "binary",
    "frontends",
    "frontend_source",
)
PIN_ARGUMENTS = (
    "controls_ledger_sha256",
    "affinity_ledger_sha256",
    "inventory_sha256",
    "frontend_ledger_sha256",
)
COMBINATIONS = tuple(
    e + "/" + r
    for e in ("soft_affinity", "uniform")
    for r in ("sdk_transform_position_m", "sdk_aabb_center_m")
)


def add_parent_arguments(parser):
    for name in ("parent_position_results", "parent_position_source", *PATH_ARGUMENTS):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    for name in ("parent_position_ledger_sha256", *PIN_ARGUMENTS):
        parser.add_argument("--" + name.replace("_", "-"), required=True)


def _plain_root(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink parent path")
    require(path.is_dir(), "parent directory missing")
    return path


def _source_files(root):
    require(
        not any(p.is_symlink() for d in ("src", "tests", "tools") for p in (root / d).rglob("*")),
        "symlink historical source",
    )
    return source_identity(root)


def _inspect(directory, source, ledger_pin):
    require(
        type(ledger_pin) is str and re.fullmatch("[0-9a-f]{64}", ledger_pin) is not None,
        "invalid parent ledger pin",
    )
    ledger = directory / "case-results.json"
    require(not ledger.is_symlink() and digest(ledger) == ledger_pin, "position ledger pin differs")
    cases = json.loads(ledger.read_bytes())
    require(
        type(cases) is list
        and len(cases) == 2
        and [c["phase"] for c in cases] == ["run", "verify"]
        and all(type(c["exit_code"]) is int and c["exit_code"] == 0 for c in cases)
        and all(c["source_sha"] == cases[0]["source_sha"] for c in cases)
        and re.fullmatch("[0-9a-f]{40}", cases[0]["source_sha"]) is not None,
        "position requires successful run and fresh verify",
    )
    files = inventory(directory / "experiment")
    names = {"report.json", "controlled-position-consumption.json"}
    names |= {f"models/{name}.json" for name in COMBINATIONS}
    names |= {
        f"training/{name}/{leaf}"
        for name in COMBINATIONS
        for leaf in ("residuals.npy", "members.json")
    }
    names |= {
        f"frames/{i:03d}/{kind}.json"
        for i in range(96)
        for kind in ("public", "labels", "corrected")
    }
    require(
        set(files) == names and all(c["output_sha256"] == files for c in cases),
        "position output members differ",
    )
    report = json.loads((directory / "experiment/report.json").read_bytes())
    require(
        report["schema"] == "soft-surface-position-development@1"
        and report["source_files"] == _source_files(source)
        and report["members"] == {k: v for k, v in files.items() if k != "report.json"}
        and report["training_attempted"] is True
        and all(
            report[k] is False
            for k in (
                "runtime_authority",
                "calibrated",
                "natural_factor_completed",
                "world_identity_assigned",
                "formal_position_reference_selected",
                "orientation_observed",
            )
        ),
        "position definition, source or authority differs",
    )
    require(
        [(f["house_index"], f["split"], f["prefix"]) for f in report["frames"]]
        == [
            (h, "train" if h <= 8 else "validation", f"frames/{(h - 1) * 8 + t:03d}")
            for h in range(1, 13)
            for t in range(8)
        ]
        and len({f["action_id"] for f in report["frames"]}) == 96,
        "position fixed frame schedule differs",
    )
    require(set(report["model_status"]) == set(COMBINATIONS), "position model matrix differs")
    states = [row["status"] for row in report["model_status"].values()]
    require(
        all(s in ("fitted", "fit_failed") for s in states)
        and type(report["models_fitted"]) is int
        and report["models_fitted"] == states.count("fitted")
        and report["training_performed"] is (states.count("fitted") > 0),
        "position fit status differs",
    )
    binding = dict(
        ledger_sha256=ledger_pin,
        actual_source_sha=cases[0]["source_sha"],
        source_files=report["source_files"],
        output_files=files,
    )
    return report, binding


@dataclass(frozen=True)
class VerifiedPositionBundle:
    root: Path
    source: Path
    _report_json: str
    _binding_json: str

    @property
    def experiment(self):
        return self.root / "experiment"

    @property
    def report(self):
        return json.loads(self._report_json)

    @property
    def binding(self):
        return json.loads(self._binding_json)

    def load_json(self, relative_path):
        require(type(relative_path) is str, "relative member must be text")
        relative = PurePosixPath(relative_path)
        require(
            not relative.is_absolute()
            and ".." not in relative.parts
            and relative.as_posix() == relative_path
            and relative.suffix == ".json",
            "invalid JSON member path",
        )
        files = self.binding["output_files"]
        require(relative_path in files, "unknown position member")
        path = self.experiment / relative_path
        require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink position member")
        raw = path.read_bytes()
        import hashlib

        require(hashlib.sha256(raw).hexdigest() == files[relative_path], "position member changed")
        return json.loads(raw)

    def assert_unchanged(self):
        report, binding = _inspect(
            _plain_root(self.root), _plain_root(self.source), self.binding["ledger_sha256"]
        )
        require(report == self.report and binding == self.binding, "position parent changed")


def _historical_command(args, source, directory):
    script = source / "tools/run_soft_position_development.py"
    require(script.is_file() and not script.is_symlink(), "historical position CLI missing")
    command = [str(args.historical_python.absolute()), str(script)]
    for name in PATH_ARGUMENTS:
        value = getattr(args, name)
        # Preserve venv executable paths: resolving python symlinks drops its environment.
        value = value.absolute() if name in ("historical_python", "sdk_python") else value.resolve()
        command.extend(["--" + name.replace("_", "-"), str(value)])
    for name in PIN_ARGUMENTS:
        value = getattr(args, name)
        require(
            type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
            "invalid historical external pin",
        )
        command.extend(["--" + name.replace("_", "-"), value])
    return [*command, "--output", str(directory / "experiment"), "--verify"]


def verify_position_parent(args):
    directory = _plain_root(args.parent_position_results)
    source = _plain_root(args.parent_position_source)
    report, binding = _inspect(directory, source, args.parent_position_ledger_sha256)
    parent = report["parent_binding"]
    require(
        parent["controls"]["ledger_sha256"] == args.controls_ledger_sha256
        and parent["affinity"]["ledger_sha256"] == args.affinity_ledger_sha256
        and parent["frontends"]["ledger_sha256"] == args.frontend_ledger_sha256
        and parent["collection_inventory_sha256"] == args.inventory_sha256,
        "position ancestor external pins differ",
    )
    command = _historical_command(args, source, directory)
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=os.pathsep.join(str(source / p) for p in ("src", "tools")),
        OPENBLAS_NUM_THREADS="1",
    )
    result = subprocess.run(command, cwd=source, env=environment, check=False, timeout=1800)
    require(result.returncode == 0, "historical position fresh refit failed")
    fresh_report, fresh_binding = _inspect(directory, source, args.parent_position_ledger_sha256)
    require(
        report == fresh_report and binding == fresh_binding, "position changed during fresh refit"
    )
    return VerifiedPositionBundle(
        directory, source, json.dumps(report, sort_keys=True), json.dumps(binding, sort_keys=True)
    )
