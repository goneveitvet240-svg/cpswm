"""Generate current test inputs through real CLIs; this never certifies the test suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "comparison/audit.json",
    "comparison/steps.jsonl.gz",
    "comparison/timing.json",
    "comparison/attribution.json",
    "full-scientific-loop.json",
    "current-p0.json",
)


def artifact_inventory(output):
    result = {}
    for name in ARTIFACTS:
        path = output / name
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("prepared input is missing or aliased: " + name)
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def consumer_environment(root, output):
    """Bind transferred inputs to actual source and bytes, not submitted env paths."""
    root, output = root.resolve(), output.resolve()
    record = json.loads((output / "preparation.json").read_text())
    if record.get("status") != "PREPARED_NOT_ACCEPTED":
        raise ValueError("preparation did not complete")
    if record.get("source_files") != source_inventory(root):
        raise ValueError("prepared inputs belong to different source")
    if record.get("artifacts") != artifact_inventory(output):
        raise ValueError("prepared input bytes changed")
    p0 = root / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
    if hashlib.sha256(p0.read_bytes()).hexdigest() != record["artifacts"]["current-p0.json"]:
        raise ValueError("current P0 differs from prepared manifest")
    return {
        "S2_AUDIT_BUNDLE": str(output / "comparison"),
        "S2_CURRENT_FULL_SCIENTIFIC_LOOP": str(output / "full-scientific-loop.json"),
    }


def source_inventory(root):
    paths = {root / name for name in ("pyproject.toml", "uv.lock", ".python-version")}
    for directory, pattern in (
        ("src", "*.py"),
        ("apps", "*.py"),
        ("tools", "*.py"),
        ("tests", "*.py"),
        ("configs", "*.json"),
        (".github/workflows", "*.yml"),
    ):
        paths.update((root / directory).rglob(pattern))
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)
    }


def plan(root, output):
    python = str(root / ".venv/bin/python")
    comparison = str(output / "comparison")
    scientific = str(output / "full-scientific-loop.json")
    main = [
        python,
        "apps/evaluation_runner/run_structure_two_comparison_audit.py",
        "--repository-root",
        str(root),
        "--output",
        comparison,
    ]
    attribution = [
        python,
        "apps/evaluation_runner/summarize_structure_two_comparison_audit.py",
        "--bundle",
        comparison,
    ]
    return [
        ("comparison_generate", main),
        ("comparison_recompute", [*main, "--verify"]),
        ("attribution_generate", attribution),
        ("attribution_recompute", [*attribution, "--verify"]),
        (
            "scientific_generate",
            [
                python,
                "apps/evaluation_runner/run_structure_two_full_scientific_loop.py",
                "--output",
                scientific,
            ],
        ),
        (
            "scientific_recompute",
            [
                python,
                "apps/evaluation_runner/run_structure_two_full_scientific_loop.py",
                "--verify",
                scientific,
            ],
        ),
        ("p0_generate", [python, "apps/evaluation_runner/generate_p0_checkpoint_manifest.py"]),
        (
            "p0_validate",
            [
                python,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-q",
                "tests/test_p0_checkpoint_manifest.py",
            ],
        ),
    ]


def prepare(root, output):
    root = root.resolve()
    output = output.absolute()
    if output.resolve() != output:
        raise ValueError("output path must be canonical without symlink aliases")
    if output.exists() or output.is_symlink():
        raise ValueError("use a new output directory; failed runs cannot be reused")
    output.mkdir(parents=True)
    frozen = source_inventory(root)
    record = dict(
        scope="CURRENT_TEST_INPUTS_ONLY_NOT_ENGINEERING_ACCEPTANCE",
        status="RUNNING",
        started_at=datetime.now(UTC).isoformat(),
        source_files=frozen,
        commands=[],
    )

    def save():
        (output / "preparation.json").write_text(json.dumps(record, indent=2) + "\n")

    save()
    p0 = root / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
    locked = {}

    def check_locked():
        for path, pin in locked.items():
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != pin:
                raise ValueError("verified input changed: " + str(path))

    try:
        # P0 is a mutable current-source index; retain its original exact bytes.
        (output / "preserved-p0.json").write_bytes(p0.read_bytes())
        for name, argv in plan(root, output):
            check_locked()
            if source_inventory(root) != frozen:
                raise ValueError("source drift before " + name)
            row = dict(name=name, argv=argv, cwd=str(root), status="RUNNING")
            record["commands"].append(row)
            save()
            with (output / (name + ".log")).open("w") as log:
                result = subprocess.run(
                    argv,
                    cwd=root,
                    env=dict(os.environ, PYTHONPATH=str(root / "src")),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            row.update(
                exit_code=result.returncode, status="PASSED" if result.returncode == 0 else "FAILED"
            )
            save()
            if result.returncode:
                raise RuntimeError(f"{name} failed with exit {result.returncode}")
            if source_inventory(root) != frozen:
                raise ValueError("source drift after " + name)
            check_locked()
            verified = {
                "comparison_recompute": [output / p for p in ARTIFACTS[:3]],
                "attribution_recompute": [output / ARTIFACTS[3]],
                "scientific_recompute": [output / ARTIFACTS[4]],
                "p0_validate": [p0],
            }.get(name, [])
            for path in verified:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("verified input missing: " + str(path))
                locked[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Publish consumer paths only after all actual generation/replay commands succeed.
        environment = {
            "S2_AUDIT_BUNDLE": str(output / "comparison"),
            "S2_CURRENT_FULL_SCIENTIFIC_LOOP": str(output / "full-scientific-loop.json"),
        }
        (output / "current-p0.json").write_bytes(p0.read_bytes())
        record.update(
            status="PREPARED_NOT_ACCEPTED",
            environment=environment,
            artifacts=artifact_inventory(output),
        )
        save()
        (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
        return record
    except BaseException as error:
        record.update(status="FAILED", error=str(error))
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(ROOT, args.output)
    print(json.dumps({"status": result["status"], "environment": result["environment"]}))


if __name__ == "__main__":
    main()
