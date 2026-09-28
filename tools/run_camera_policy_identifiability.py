"""Exhaust all two-view binary measurements on the actual controlled runtime.

The camera renders 4x4 fixture pixels. This is NOT a Unity, detection-quality,
natural-semantic or physical target-success experiment. Actual neural checkpoints
are used by the CLI; probabilities and actions are consumed by the real owner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_neural_pixel_camera_loop import (  # noqa: E402
    ARMS,
    ASSUMPTIONS,
    METHODS,
    DiagnosticViewModel,
    canonical_probabilities,
    collect_comparison_step,
    source_identity,
)
from test_joint_camera_feedback import Camera, setup  # noqa: E402
from test_native_joint_production import JointFixture  # noqa: E402
from test_neural_camera_comparison import CategoryFixture  # noqa: E402

from cpswm.system.native_neural_production import NeuralNativeProducer  # noqa: E402
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402

PATTERNS = ("00", "01", "10", "11")
SCOPE = "CONTROLLED_4X4_BINARY_MEASUREMENT_RUNTIME_NOT_UNITY_OR_NATURAL_VISION"


def require(condition, message):
    if not condition:
        raise ValueError(message)


class PatternCamera(Camera):
    """Physical headings are fixture state; only requested view controls pixels."""

    def __init__(self, transition, pattern):
        require(pattern in PATTERNS, "undeclared measurement pattern")
        super().__init__(transition)
        self.outcomes = dict(zip((225.0, 315.0), (v == "1" for v in pattern), strict=True))
        self.heading = 270.0
        self.visits = []

    def execute(self, command):
        require(command.action in ("RotateLeft", "RotateRight"), "not a diagnostic rotation")
        heading = (
            self.heading + command.degrees * (1 if command.action == "RotateRight" else -1)
        ) % 360
        require(heading in self.outcomes, "unregistered diagnostic heading")
        self.heading, self.bright = heading, self.outcomes[heading]
        delivery = super().execute(command)
        self.visits.append(heading)
        return delivery


def checkpoint_for(checkpoints, method):
    require(method in METHODS, "undeclared method")
    return checkpoints / (method if method in ARMS else ARMS[0]) / "checkpoint"


def run_case(directory, *, pattern, method, checkpoint=None):
    require(pattern in PATTERNS and method in METHODS, "undeclared case")
    directory.mkdir(parents=True, exist_ok=False)
    pin, arm = None, None
    joint = JointFixture()
    if checkpoint is not None:
        manifest = json.loads((checkpoint / "manifest.json").read_text())
        arm = method if method in ARMS else ARMS[0]
        require(manifest["arm"] == arm, "checkpoint arm differs from method")
        pin = hashlib.sha256((checkpoint / "manifest.json").read_bytes()).hexdigest()
        joint = NeuralNativeProducer(joint, checkpoint, manifest_sha256=pin)
    decoder = CategoryFixture()
    stream, store, transition, _, start = setup(
        directory / "state.sqlite", decoder, joint, feedback=method in ARMS
    )
    stream._producer.output = None
    camera, model = PatternCamera(transition, pattern), DiagnosticViewModel(decoder)
    core = stream._system.core
    native_before = native_content_sha256(core._particle_workspace.state_payload())
    ledger_before = core._hybrid_loop.ledger.export_state()
    initial = canonical_probabilities(stream.current_joint_decision_view())
    rows, stopped = [], False
    when = start + timedelta(seconds=2)
    try:
        # Same three decision opportunities as the actual two-view comparison.
        for _ in range(3):
            before = canonical_probabilities(stream.current_joint_decision_view())
            result = collect_comparison_step(stream, model, camera, method, when)
            if result.command is None:
                stopped = True
                break
            require(result.delivery.success, "fixture execution failed")
            after = canonical_probabilities(stream.current_joint_decision_view())
            rows.append(
                dict(
                    action=result.command.action,
                    degrees=result.command.degrees,
                    heading=camera.heading,
                    outcome=decoder.decode(
                        result.delivery.observations, cutoff=result.delivery.received_at
                    ),
                    prior=before,
                    posterior=after,
                    probabilities_changed=before != after,
                )
            )
            when = result.delivery.received_at + timedelta(seconds=1)
        return dict(
            pattern=pattern,
            method=method,
            checkpoint_arm=arm,
            checkpoint_manifest_sha256=pin,
            initial=initial,
            final=canonical_probabilities(stream.current_joint_decision_view()),
            actions=rows,
            stopped=stopped,
            camera_calls=camera.calls,
            feedback_updates=len(stream.joint_observation_updates()),
            neural_calls=joint.calls if checkpoint is not None else 0,
            native_unchanged=native_before
            == native_content_sha256(core._particle_workspace.state_payload()),
            ledger_unchanged=ledger_before == core._hybrid_loop.ledger.export_state(),
        )
    finally:
        store.close()


def same_value(actual, expected, *, path="result"):
    """Compare every reported field; only floating arithmetic gets a tolerance."""
    if type(expected) is float:
        require(
            type(actual) is float
            and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12),
            "recomputed field differs: " + path,
        )
    elif isinstance(expected, dict):
        require(type(actual) is dict and set(actual) == set(expected), "field set differs: " + path)
        for key, value in expected.items():
            same_value(actual[key], value, path=path + "." + key)
    elif isinstance(expected, list):
        require(type(actual) is list and len(actual) == len(expected), "list differs: " + path)
        for index, value in enumerate(expected):
            same_value(actual[index], value, path=f"{path}[{index}]")
    else:
        require(type(actual) is type(expected) and actual == expected, "field differs: " + path)


def trace(row):
    return [
        {key: step[key] for key in ("action", "degrees", "heading", "outcome")}
        for step in row["actions"]
    ]


def summarize(rows):
    expected = {(pattern, method) for pattern in PATTERNS for method in METHODS}
    require(
        len(rows) == len(expected) and {(r["pattern"], r["method"]) for r in rows} == expected,
        "incomplete or duplicate four-pattern six-method matrix",
    )
    reference = rows[0]["initial"]
    indexed = {(r["pattern"], r["method"]): r for r in rows}
    for row in rows:
        same_value(row["initial"], reference, path="common initial posterior")
        require(
            row["stopped"] and row["native_unchanged"] and row["ledger_unchanged"],
            "missing stop or native/ledger preservation",
        )
        require(row["camera_calls"] == len(row["actions"]) in (1, 2), "invalid measurement count")
        feedback = row["method"] in ARMS
        require(
            row["feedback_updates"] == (len(row["actions"]) if feedback else 0),
            "feedback treatment differs",
        )
        require(
            all(step["probabilities_changed"] is feedback for step in row["actions"]),
            "feedback did not change probabilities or control did",
        )
        if not feedback:
            same_value(row["final"], row["initial"], path="control posterior")
    matches = []
    for pattern in PATTERNS:
        reference_trace = trace(indexed[pattern, "no_feedback"])
        matches.append(
            dict(
                pattern=pattern,
                all_neural_match_no_feedback=all(
                    trace(indexed[pattern, arm]) == reference_trace for arm in ARMS
                ),
                right_scan_matches_no_feedback=trace(indexed[pattern, "scan_right_first"])
                == reference_trace,
                neural_actions=len(reference_trace),
                left_scan_actions=len(indexed[pattern, "scan_left_first"]["actions"]),
            )
        )
    return dict(
        scope=SCOPE,
        complete_cases=len(rows),
        actual_unity_episodes=0,
        natural_vision_frames=0,
        physical_target_success_evaluated=False,
        same_initial_priors=True,
        all_neural_match_no_feedback=all(r["all_neural_match_no_feedback"] for r in matches),
        all_right_scan_match_no_feedback=all(r["right_scan_matches_no_feedback"] for r in matches),
        patterns=matches,
    )


def run_matrix(output, checkpoints):
    output.mkdir(parents=True, exist_ok=False)
    source, files = source_identity()
    plan = [dict(pattern=p, method=m, status="PENDING") for p in PATTERNS for m in METHODS]
    rows = []
    failures = []
    for cell in plan:
        cell["status"] = "RUNNING"
        (output / "matrix.json").write_text(json.dumps(plan, indent=2) + "\n")
        try:
            row = run_case(
                output / cell["pattern"] / cell["method"],
                pattern=cell["pattern"],
                method=cell["method"],
                checkpoint=checkpoint_for(checkpoints, cell["method"]),
            )
            rows.append(row)
            cell["status"] = "COMPLETE"
        except Exception as exc:
            cell["status"], cell["error"] = "FAILED", repr(exc)
            failures.append(cell.copy())
        (output / "matrix.json").write_text(json.dumps(plan, indent=2) + "\n")
        (output / "partial-results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(json.dumps(cell), flush=True)
    require(not failures, "controlled matrix has failures; all planned cells retained")
    require(source_identity() == (source, files), "source changed during matrix")
    report = dict(
        scope=SCOPE,
        source_sha256=source,
        source_files=files,
        assumptions=ASSUMPTIONS,
        rows=rows,
        summary=summarize(rows),
    )
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")


def verify_matrix(output, checkpoints):
    report = json.loads((output / "result.json").read_text())
    source, files = source_identity()
    require(
        set(report) == {"scope", "source_sha256", "source_files", "assumptions", "rows", "summary"},
        "unregistered report fields or claims",
    )
    require(
        report["scope"] == SCOPE and report["assumptions"] == ASSUMPTIONS,
        "controlled scope or fixed assumptions changed",
    )
    require(
        (report["source_sha256"], report["source_files"]) == (source, files),
        "source differs from executed matrix",
    )
    same_value(report["summary"], summarize(report["rows"]), path="summary")
    plan = json.loads((output / "matrix.json").read_text())
    require(
        plan == [dict(pattern=p, method=m, status="COMPLETE") for p in PATTERNS for m in METHODS],
        "plan incomplete or altered",
    )
    recomputed = []
    with tempfile.TemporaryDirectory(prefix="cpswm-policy-recompute-") as temporary:
        for row in report["rows"]:
            actual = run_case(
                Path(temporary) / row["pattern"] / row["method"],
                pattern=row["pattern"],
                method=row["method"],
                checkpoint=checkpoint_for(checkpoints, row["method"]),
            )
            same_value(row, actual)
            recomputed.append(actual)
    require(source_identity() == (source, files), "source changed during reexecution")
    summary = summarize(recomputed)
    (output / "verified-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(2)
    (run_matrix if args.mode == "run" else verify_matrix)(args.output, args.checkpoints)
