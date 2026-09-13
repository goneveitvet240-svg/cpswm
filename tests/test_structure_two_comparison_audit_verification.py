"""Real-CLI dependency attacks. Integration test performs one uncached full replay."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from structure_two_comparison_audit_adversary import CASES, build_attack

from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/reviews/data/structure_two_comparison_audit_window2_r1_2026-09-11"
BUNDLE = Path(os.environ.get("S2_AUDIT_BUNDLE", str(RESULTS / "bundle_v2")))
CLI = ROOT / "apps/evaluation_runner/summarize_structure_two_comparison_audit.py"


@pytest.mark.parametrize(
    "raw,error",
    [
        ('{"x":1,"x":2}', "DUPLICATE_JSON_KEY"),
        ('{"x":NaN}', "NONFINITE_JSON_NUMBER"),
        ('{"x":Infinity}', "NONFINITE_JSON_NUMBER"),
    ],
)
def test_strict_json(raw, error):
    with pytest.raises(ValueError, match=error):
        audit.strict_json(raw)


def test_difference_reports_order_multiplicity_and_type():
    assert audit.first_difference([1, 2], [2, 1]) == "$[0]"
    assert ".length" in audit.first_difference([1, 1], [1])
    assert "type" in audit.first_difference(True, 1)
    assert audit.first_difference({"a": [1]}, {"a": [1]}) is None


def cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=3600,
    )


def test_cli_refuses_external_reference_argument():
    result = cli("--bundle", BUNDLE, "--verify", "--expected-payload", BUNDLE / "audit.json")
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_real_cli_complete_forgery_matrix_and_valid_fresh_positive(tmp_path):
    # Required, not skipped: generate bundle_v2 through the real main CLI first.
    assert BUNDLE.exists(), "run the main CLI into bundle_v2 before integration tests"
    evidence = Path(os.environ.get("S2_AUDIT_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    commands = ["--bundle", BUNDLE]
    attacks = []
    details = []
    for case in CASES:
        target = tmp_path / case
        details.append(build_attack(BUNDLE, target, case, ROOT))
        attacks.append(target)
        commands.extend(["--bundle", target])
    # File consistency is intentionally weak and must say so even for the R1 forgery.
    weak = cli("--bundle", attacks[0], "--check-file-consistency")
    assert weak.returncode == 0, weak.stderr
    weak_payload = json.loads(weak.stdout.splitlines()[-1])
    assert weak_payload["status"] == "FILE_CONSISTENCY_ONLY"
    assert weak_payload["fresh_replay_performed"] is False
    (evidence / "r1_file_consistency_only.log").write_text(weak.stdout + weak.stderr)
    result = cli(*commands, "--verify")
    (evidence / "adversarial_cli.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 1, result.stdout + result.stderr
    response = json.loads(result.stdout.splitlines()[-1])
    assert response["fresh_replay_performed"] is True
    records = response["results"]
    assert records[0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH", records[0]
    assert records[0]["steps"] == len(audit.load_bundle(BUNDLE).rows)
    assert records[0]["formal_scientific_verification"] is False
    assert len(records) == 1 + len(CASES)
    for case, record in zip(CASES, records[1:], strict=True):
        assert record["status"] == "REJECTED", (case, record)
        assert record["error"], case
        if case not in {
            "source_binding",
            "attribution_only",
            "config_selection",
            "seed_split",
            "source_version",
        }:
            assert "FRESH_REPLAY_STEP_MISMATCH" in record["error"], (case, record)
    (evidence / "adversarial_matrix.json").write_text(
        json.dumps(
            {
                "reference": (
                    "real full run_audit called internally in CLI, no mocks or cached reference"
                ),
                "cases": details,
                "result": response,
            },
            indent=2,
        )
        + "\n"
    )
