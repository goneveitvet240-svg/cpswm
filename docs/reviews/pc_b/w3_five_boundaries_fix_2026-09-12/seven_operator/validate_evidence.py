"""Validate the stage-3 evidence bundle and emit a non-self-referential manifest."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw_trace(path: Path) -> tuple[dict[str, object], str]:
    body = gzip.decompress(path.read_bytes())
    for encoding in ("utf-8", "cp936"):
        try:
            return json.loads(body.decode(encoding)), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"unsupported raw trace encoding: {path}")


def source_aggregate() -> str:
    files = {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted((ROOT / "src").rglob("*.py"))
    }
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    json_files = sorted(
        path
        for path in OUT.glob("*.json")
        if path.name != "artifact_manifest.json"
    )
    parsed = {
        path.name: json.loads(path.read_text(encoding="utf-8")) for path in json_files
    }
    traces: dict[str, object] = {}
    for path in sorted(OUT.glob("continuous_current_*.json.gz")):
        payload, encoding = load_raw_trace(path)
        assert payload["completed"] is True
        assert payload["source_before"] == payload["source_after"]
        traces[path.name] = {
            "encoding": encoding,
            "steps": len(payload["steps"]),
            "calls": len(payload["calls"]),
            "completed": payload["completed"],
        }
    junits = {}
    for path in sorted(OUT.glob("pytest_*.xml")):
        root = ET.parse(path).getroot()
        cases = root.findall(".//testcase")
        failures = root.findall(".//failure")
        errors = root.findall(".//error")
        skipped = root.findall(".//skipped")
        assert not failures and not errors and not skipped
        junits[path.name] = {"tests": len(cases), "passed": len(cases)}

    environment = parsed["environment_and_source_binding.json"]
    commands = parsed["commands.json"]
    matrix = parsed["connection_and_scenario_matrix.json"]
    gaps = parsed["capability_gaps.json"]
    assert environment["source_unchanged"] is True
    assert source_aggregate() == environment["source_after"]["aggregate_sha256"]
    assert commands["all_command_outcomes_as_expected"] is True
    assert all(row["outcome_as_expected"] for row in commands["records"])
    gap_row = next(row for row in commands["records"] if row["label"] == "capability_gap_probe")
    assert gap_row["exit_code"] == 2
    assert gaps["all_required_capabilities_present"] is False
    assert matrix["claims"]["default_full_joint_backbone_operational"] is False
    assert matrix["claims"]["scientific_benefit_verified"] is False
    assert sum(item["tests"] for item in junits.values()) == 74
    assert not subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            f"{environment['last_commit_touching_src']}..{environment['git_head']}",
            "--",
            "src",
        ],
        cwd=ROOT,
        text=True,
    ).strip()

    text_suffixes = {".json", ".log", ".md", ".py", ".xml"}
    whitespace_problems = []
    for path in sorted(item for item in OUT.iterdir() if item.suffix in text_suffixes):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip(" \t") != line:
                whitespace_problems.append(f"{path.name}:{line_number}: trailing whitespace")
        if text and path.suffix != ".xml" and not text.endswith("\n"):
            whitespace_problems.append(f"{path.name}: missing final newline")
    assert not whitespace_problems, whitespace_problems
    diff_check = subprocess.run(
        ["git", "diff", "--check"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert diff_check.returncode == 0
    current_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    current_head_source_diff = subprocess.check_output(
        ["git", "diff", "--name-only", f"{environment['git_head']}..{current_head}", "--", "src"],
        cwd=ROOT,
        text=True,
    ).strip().splitlines()
    assert not current_head_source_diff

    files = {}
    for path in sorted(item for item in OUT.iterdir() if item.is_file()):
        if path.name == "artifact_manifest.json":
            continue
        files[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {
        "classification": "engineering causal diagnostic evidence manifest",
        "manifest_excludes_itself": True,
        "git_head": environment["git_head"],
        "current_worktree_head_at_validation": current_head,
        "current_head_vs_tested_head_src_diff_names": current_head_source_diff,
        "last_commit_touching_src": environment["last_commit_touching_src"],
        "source_aggregate_sha256": environment["source_after"]["aggregate_sha256"],
        "json_files_parsed": sorted(parsed),
        "raw_traces": traces,
        "junit": junits,
        "files": files,
        "validation": {
            "all_utf8_json_parsed": True,
            "all_raw_traces_parsed_and_completed": True,
            "all_raw_trace_source_snapshots_unchanged": True,
            "all_junit_green": True,
            "junit_total_passed": 74,
            "capability_gap_probe_exit_2_preserved": True,
            "default_full_joint_claim_false": True,
            "scientific_benefit_claim_false": True,
            "production_source_unchanged": True,
            "tracked_git_diff_check_exit_0": True,
            "tracked_git_diff_check_stdout": diff_check.stdout,
            "tracked_git_diff_check_stderr": diff_check.stderr,
            "audit_text_files_have_no_trailing_whitespace": True,
        },
        "command": [str(Path(sys.executable).resolve()), str(Path(__file__).resolve())],
        "exit_code": 0,
    }
    (OUT / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "files": len(files),
                "raw_traces": len(traces),
                "junit_passed": 74,
                "source_unchanged": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
