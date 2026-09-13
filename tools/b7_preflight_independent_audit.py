"""Independent B7 audit runner without a pytest installation.

This runner executes the exact 43 component checks from the A delivery by
calling their test functions directly, then exercises additional prefix,
duplicate, CLI and nested-leakage attacks.  It does not train, execute a
method arm, or generate any reserved validation/confirmation world.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
import types
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
for path in (str(TESTS), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)


class _Approx:
    def __init__(self, expected: float) -> None:
        self.expected = expected

    def __eq__(self, actual: object) -> bool:
        return isinstance(actual, (int, float)) and math.isclose(
            float(actual), self.expected, rel_tol=1e-12, abs_tol=1e-12
        )


@contextlib.contextmanager
def _raises(expected: type[BaseException] | tuple[type[BaseException], ...], match: str | None = None) -> Iterator[None]:
    try:
        yield
    except expected as error:
        if match is not None and re.search(match, str(error)) is None:
            raise AssertionError(
                f"exception text {str(error)!r} does not match {match!r}"
            ) from error
    else:
        raise AssertionError(f"expected {expected!r} was not raised")


def _install_pytest_shim() -> None:
    module = types.ModuleType("pytest")

    def fixture(*args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    class Mark:
        @staticmethod
        def parametrize(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            return lambda function: function

    module.fixture = fixture  # type: ignore[attr-defined]
    module.mark = Mark()  # type: ignore[attr-defined]
    module.raises = _raises  # type: ignore[attr-defined]
    module.approx = lambda expected: _Approx(expected)  # type: ignore[attr-defined]
    sys.modules["pytest"] = module


_install_pytest_shim()
data_tests = importlib.import_module("test_structure_two_data_preflight")
d0_tests = importlib.import_module("test_d0_shift_scenarios")

from cpswm.contracts import ActorEvidenceTrack  # noqa: E402
from cpswm.data_preflight.visible_prefix import export_visible_prefix  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _call_with_tmp(function: Callable[..., Any], *args: Any) -> None:
    with tempfile.TemporaryDirectory(prefix="cpswm-b7-audit-") as directory:
        function(Path(directory), *args)


def _delivery_cases() -> list[tuple[str, Callable[[], None]]]:
    sample = data_tests.sample()
    cases: list[tuple[str, Callable[[], None]]] = [
        ("data.visible_legal", lambda: data_tests.test_visible_prefix_preserves_legal_fields_and_no_global_truth(sample)),
        ("data.late_detection", lambda: data_tests.test_late_detection_is_pending_until_it_arrives(sample)),
        ("data.late_actor", lambda: data_tests.test_late_actor_evidence_waits_for_both_arrival_and_parent(sample)),
        ("data.future_invariance", lambda: data_tests.test_no_future_opportunity_or_support_changes_earlier_features(sample)),
    ]
    for outcome, strength in (
        ("not_observed", 0.0),
        ("ambiguous", 0.0),
        ("verified_absence", 0.7),
    ):
        cases.append(
            (
                f"data.missingness.{outcome}",
                lambda outcome=outcome, strength=strength: data_tests.test_missingness_is_not_fabricated_negative_evidence(
                    sample, outcome, strength
                ),
            )
        )
    for attack in (
        "duplicate",
        "orphan",
        "arrival_missing",
        "arrival_early",
        "session",
        "unselected",
        "mutated_result",
        "oracle_actor",
    ):
        cases.append(
            (
                f"data.invalid.{attack}",
                lambda attack=attack: data_tests.test_visible_input_boundary_rejects_invalid_paths(
                    sample, attack
                ),
            )
        )
    cases.extend(
        [
            ("data.capture_separation", lambda: _call_with_tmp(data_tests.test_capture_orders_real_interface_calls_and_separates_truth)),
            ("data.capture_known_failure", lambda: _call_with_tmp(data_tests.test_simulator_failure_is_recorded_not_forged_success)),
        ]
    )
    for fault in ("nan", "mismatch", "interrupt"):
        cases.append(
            (
                f"data.capture_uncertain.{fault}",
                lambda fault=fault: _call_with_tmp(data_tests.test_uncertain_capture_never_retries_action, fault),
            )
        )
    cases.extend(
        [
            ("data.capture_action_contract", lambda: _call_with_tmp(data_tests.test_out_of_contract_action_rejected_before_execution)),
            ("data.simulator_preflight_truthful", data_tests.test_preflight_does_not_claim_simulator_execution),
            ("data.train_profile", data_tests.test_train_profile_exact_grain_and_explicit_full_scope_gaps),
        ]
    )
    for attack in (None, "confirmation", "truth", "overwrite"):
        label = attack or "legal"
        cases.append(
            (
                f"data.cli.{label}",
                lambda attack=attack: _call_with_tmp(
                    data_tests.test_actual_export_cli_positive_and_rejected_envelopes,
                    sample,
                    attack,
                ),
            )
        )
    cases.extend(
        [
            ("data.empty_prefix", lambda: data_tests.test_all_future_input_returns_empty_not_negative(sample)),
            ("data.mutable_actor_revalidated", lambda: data_tests.test_mutable_actor_probabilities_are_revalidated(sample)),
            ("d0.checked_config", d0_tests.test_checked_in_d0_config_replays_the_frozen_suite),
            ("d0.deterministic_one_factor", d0_tests.test_d0_suite_is_deterministic_and_changes_exactly_one_bound_factor),
            ("d0.preperiod", d0_tests.test_d0_observation_shift_has_an_identical_pre_period_and_post_policy_change),
            ("d0.paired_randomness", d0_tests.test_d0_paired_randomness_reuses_draws_independently_of_policy_identity),
            ("d0.shared_session", d0_tests.test_d0_pairs_have_one_shared_session_and_trace_without_splice_shortcut),
            ("d0.nonidentifiable_without_people", d0_tests.test_d0_actor_and_owner_habit_changes_are_observationally_equivalent_without_people),
            ("d0.truth_excluded", d0_tests.test_candidate_input_excludes_truth_cause_actor_and_regime_labels),
            ("d0.baseline_leakage_metric", d0_tests.test_logged_policy_location_baseline_exposes_actor_to_habit_leakage),
            ("d0.abstention_scores", d0_tests.test_non_identifiable_cases_reward_explicit_abstention_with_proper_scores),
            (
                "d0.actor_track.controlled_noise",
                lambda: d0_tests.test_actor_evidence_tracks_break_d0_actor_habit_equivalence(
                    ActorEvidenceTrack.CONTROLLED_NOISE
                ),
            ),
            (
                "d0.actor_track.oracle",
                lambda: d0_tests.test_actor_evidence_tracks_break_d0_actor_habit_equivalence(
                    ActorEvidenceTrack.ORACLE
                ),
            ),
            ("d0.controlled_uncertainty", d0_tests.test_controlled_actor_evidence_is_uncertain_and_gt_free),
            ("d0.truth_multifactor_rejected", d0_tests.test_d0_truth_rejects_a_pair_that_changes_multiple_factors),
            ("d0.identical_fingerprint", d0_tests.test_d0_factor_fingerprints_report_no_change_for_identical_values),
        ]
    )
    if len(cases) != 43:
        raise AssertionError(f"delivery matrix should contain 43 cases, got {len(cases)}")
    return cases


def _run_delivery() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, function in _delivery_cases():
        started = time.perf_counter()
        try:
            function()
        except BaseException as error:
            results.append(
                {
                    "name": name,
                    "status": "failed",
                    "seconds": time.perf_counter() - started,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
        else:
            results.append(
                {"name": name, "status": "passed", "seconds": time.perf_counter() - started}
            )
    return results


def _legal_sample() -> tuple[Any, Any, Any, dict[Any, Any]]:
    op, detection, actor = data_tests.sample()
    arrivals = {
        op.metadata.record_id: op.opportunity_time,
        detection.metadata.record_id: detection.detection_time,
        actor.metadata.record_id: actor.evidence_time,
    }
    return op, detection, actor, arrivals


def _probe_boundary_and_receipt() -> dict[str, Any]:
    op, detection, actor, arrivals = _legal_sample()
    view = export_visible_prefix(
        (op,),
        (detection,),
        actor_evidence=(actor,),
        received_at=arrivals,
        cutoff=op.opportunity_time,
    )
    model = view.model_input()
    provenance = json.loads(view.provenance_json)
    expected_hashes = {
        str(item.metadata.record_id): content_sha256(item) for item in (op, detection, actor)
    }
    observed_hashes = {
        item["record_id"]: item["content_sha256"] for item in provenance["included_records"]
    }
    return {
        "status": "defense_passed",
        "exact_cutoff_included": bool(model["observations"][0]["actor_evidence"]),
        "feature_hash_matches": provenance["feature_sha256"] == content_sha256(model),
        "record_hashes_match": observed_hashes == expected_hashes,
    }


def _probe_reordering() -> dict[str, Any]:
    run = data_tests.D0ShiftScenarioGenerator().generate(
        actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE
    ).cases[0].model_input.control_run
    detections = tuple(item for item in run.detection_results if item.detection_time is not None)[:2]
    detection_ids = {item.observation_opportunity_id for item in detections}
    opportunities = tuple(
        item for item in run.observation_opportunities if item.metadata.record_id in detection_ids
    )
    arrivals = {
        item.metadata.record_id: item.opportunity_time for item in opportunities
    } | {
        item.metadata.record_id: item.detection_time for item in detections
    }
    cutoff = max(item.detection_time for item in detections) + timedelta(seconds=1)
    first = export_visible_prefix(
        opportunities, detections, received_at=arrivals, cutoff=cutoff
    )
    replay = export_visible_prefix(
        tuple(reversed(opportunities)),
        tuple(reversed(detections)),
        received_at=dict(reversed(tuple(arrivals.items()))),
        cutoff=cutoff,
    )
    return {
        "status": "defense_passed" if first == replay else "vulnerable",
        "observation_count": len(first.model_input()["observations"]),
        "identical": first == replay,
    }


def _probe_semantic_actor_duplicate() -> dict[str, Any]:
    op, detection, actor, arrivals = _legal_sample()
    legal = export_visible_prefix(
        (op,),
        (detection,),
        actor_evidence=(actor,),
        received_at=arrivals,
        cutoff=op.opportunity_time,
    )
    duplicate = actor.model_copy(
        update={"metadata": actor.metadata.model_copy(update={"record_id": uuid4()})}
    )
    attacked_arrivals = dict(arrivals)
    attacked_arrivals[duplicate.metadata.record_id] = duplicate.evidence_time
    try:
        attacked = export_visible_prefix(
            (op,),
            (detection,),
            actor_evidence=(actor, duplicate),
            received_at=attacked_arrivals,
            cutoff=op.opportunity_time,
        )
    except ValueError as error:
        return {"status": "defense_passed", "rejection": str(error)}
    row = attacked.model_input()["observations"][0]
    return {
        "status": "vulnerable",
        "finding_id": "B7-DUPLICATE-ACTOR-CLUSTER",
        "legal_actor_entries": 1,
        "attacked_actor_entries": len(row["actor_evidence"]),
        "duplicate_payloads_identical": row["actor_evidence"][0] == row["actor_evidence"][1],
        "feature_hash_changed": json.loads(legal.provenance_json)["feature_sha256"]
        != json.loads(attacked.provenance_json)["feature_sha256"],
        "evidence_cluster_id": str(actor.evidence_cluster_id),
    }


def _probe_duplicate_json_keys() -> dict[str, Any]:
    op, detection, actor, _ = _legal_sample()
    remainder = {
        "opportunities": [op.model_dump(mode="json")],
        "detections": [detection.model_dump(mode="json")],
        "actor_evidence": [actor.model_dump(mode="json")],
        "received_at": {
            str(op.metadata.record_id): op.opportunity_time.isoformat(),
            str(detection.metadata.record_id): detection.detection_time.isoformat(),
            str(actor.metadata.record_id): actor.evidence_time.isoformat(),
        },
    }
    raw = '{"partition":"confirmation","partition":"development",' + json.dumps(
        remainder, separators=(",", ":")
    )[1:]
    with tempfile.TemporaryDirectory(prefix="cpswm-b7-json-duplicate-") as directory:
        root = Path(directory)
        source, output = root / "input.json", root / "output.json"
        source.write_text(raw, encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/structure_two_data_preflight.py"),
                "export-visible",
                "--input",
                str(source),
                "--output",
                str(output),
                "--cutoff",
                op.opportunity_time.isoformat(),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=dict(os.environ, PYTHONPATH=str(SRC)),
            timeout=30,
        )
        parsed = json.loads(output.read_text()) if output.exists() else None
    if completed.returncode != 0:
        return {
            "status": "defense_passed",
            "exit_code": completed.returncode,
            "stderr": completed.stderr,
        }
    return {
        "status": "vulnerable",
        "finding_id": "B7-DUPLICATE-JSON-KEY",
        "exit_code": completed.returncode,
        "raw_contains_confirmation_and_development": True,
        "reported_partition": parsed["audit_only"]["declared_partition"],
        "output_created": parsed is not None,
        "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


def _probe_nested_request_leakage() -> dict[str, Any]:
    controller = data_tests.FakeController()
    with tempfile.TemporaryDirectory(prefix="cpswm-b7-nested-request-") as directory:
        capture = data_tests.session(Path(directory), controller)
        candidate = capture.capture(
            {
                "action": "Pass",
                "nested": {"evaluator_truth": {"true_actor": "hidden-person"}},
            }
        )
        persisted = json.loads(
            (Path(directory) / "capture/observations/000000.json").read_text()
        )
    serialized = json.dumps(candidate, sort_keys=True)
    leaked = "hidden-person" in serialized and persisted == candidate
    return {
        "status": "vulnerable" if leaked else "defense_passed",
        "finding_id": "B7-NESTED-REQUEST-LEAK" if leaked else None,
        "controller_called": len(controller.calls) == 1,
        "candidate_contains_nested_truth": "hidden-person" in serialized,
        "persisted_candidate_matches": persisted == candidate,
    }


def _probe_future_recorded_time() -> dict[str, Any]:
    op, detection, _actor, _arrivals = _legal_sample()
    future_recorded = op.opportunity_time + timedelta(days=3)
    attacked_op = op.model_copy(
        update={
            "metadata": op.metadata.model_copy(update={"recorded_time": future_recorded})
        }
    )
    view = export_visible_prefix(
        (attacked_op,),
        (detection,),
        received_at={
            attacked_op.metadata.record_id: attacked_op.opportunity_time,
            detection.metadata.record_id: detection.detection_time,
        },
        cutoff=op.opportunity_time,
    )
    included = bool(view.model_input()["observations"])
    return {
        "status": "vulnerable" if included else "defense_passed",
        "finding_id": "B7-ARRIVAL-PRECEDES-RECORDED-TIME" if included else None,
        "cutoff": op.opportunity_time.isoformat(),
        "declared_received_at": attacked_op.opportunity_time.isoformat(),
        "recorded_time": future_recorded.isoformat(),
        "record_included": included,
        "classification": "temporal-consistency risk; recorded_time semantics need owner confirmation",
    }


def _probe_actor_prior_distinction() -> dict[str, Any]:
    op, detection, actor, arrivals = _legal_sample()
    keys = list(actor.reference_actor_prior)
    altered_prior = dict(actor.reference_actor_prior)
    altered_prior[keys[0]], altered_prior[keys[1]] = (
        altered_prior[keys[1]],
        altered_prior[keys[0]],
    )
    if altered_prior == actor.reference_actor_prior:
        altered_prior = {keys[0]: 0.5, keys[1]: 0.25, keys[2]: 0.25}
    altered = actor.model_copy(update={"reference_actor_prior": altered_prior})
    altered_arrivals = dict(arrivals)
    original = export_visible_prefix(
        (op,), (detection,), actor_evidence=(actor,), received_at=arrivals, cutoff=op.opportunity_time
    )
    changed = export_visible_prefix(
        (op,), (detection,), actor_evidence=(altered,), received_at=altered_arrivals, cutoff=op.opportunity_time
    )
    original_actor = original.model_input()["observations"][0]["actor_evidence"][0]
    changed_actor = changed.model_input()["observations"][0]["actor_evidence"][0]
    passed = (
        original_actor["actor_posterior"] == changed_actor["actor_posterior"]
        and original_actor["reference_actor_prior"] != changed_actor["reference_actor_prior"]
        and json.loads(original.provenance_json)["feature_sha256"]
        != json.loads(changed.provenance_json)["feature_sha256"]
    )
    return {
        "status": "defense_passed" if passed else "vulnerable",
        "posterior_preserved": original_actor["actor_posterior"] == changed_actor["actor_posterior"],
        "prior_distinct": original_actor["reference_actor_prior"] != changed_actor["reference_actor_prior"],
        "receipt_changed": json.loads(original.provenance_json)["feature_sha256"]
        != json.loads(changed.provenance_json)["feature_sha256"],
    }


def _run_extensions() -> list[dict[str, Any]]:
    probes = [
        ("boundary_and_receipt", _probe_boundary_and_receipt),
        ("input_reordering", _probe_reordering),
        ("semantic_actor_duplicate", _probe_semantic_actor_duplicate),
        ("duplicate_json_keys", _probe_duplicate_json_keys),
        ("nested_request_leakage", _probe_nested_request_leakage),
        ("future_recorded_time", _probe_future_recorded_time),
        ("actor_prior_distinction", _probe_actor_prior_distinction),
    ]
    results = []
    for name, function in probes:
        started = time.perf_counter()
        try:
            result = function()
        except BaseException as error:
            result = {
                "status": "probe_error",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        result["name"] = name
        result["seconds"] = time.perf_counter() - started
        results.append(result)
    return results


def _write_junit(
    path: Path, delivery: list[dict[str, Any]], extensions: list[dict[str, Any]]
) -> None:
    suites = ET.Element("testsuites")
    delivery_suite = ET.SubElement(
        suites,
        "testsuite",
        name="b7-delivery-43",
        tests=str(len(delivery)),
        failures=str(sum(item["status"] != "passed" for item in delivery)),
        errors="0",
        time=str(sum(item["seconds"] for item in delivery)),
    )
    for item in delivery:
        case = ET.SubElement(
            delivery_suite,
            "testcase",
            classname="b7.delivery",
            name=item["name"],
            time=str(item["seconds"]),
        )
        if item["status"] != "passed":
            failure = ET.SubElement(
                case,
                "failure",
                type=item.get("error_type", "AssertionError"),
                message=item.get("error", "delivery check failed"),
            )
            failure.text = item.get("traceback", "")
    extension_suite = ET.SubElement(
        suites,
        "testsuite",
        name="b7-adversarial-extensions",
        tests=str(len(extensions)),
        failures=str(sum(item["status"] == "vulnerable" for item in extensions)),
        errors=str(sum(item["status"] == "probe_error" for item in extensions)),
        time=str(sum(item["seconds"] for item in extensions)),
    )
    for item in extensions:
        case = ET.SubElement(
            extension_suite,
            "testcase",
            classname="b7.adversarial",
            name=item["name"],
            time=str(item["seconds"]),
        )
        if item["status"] == "vulnerable":
            failure = ET.SubElement(
                case,
                "failure",
                type=item.get("finding_id", "AdversarialDefenseFailure"),
                message="adversarial input was accepted or leaked into a protected output",
            )
            failure.text = json.dumps(item, sort_keys=True)
        elif item["status"] == "probe_error":
            error = ET.SubElement(
                case,
                "error",
                type=item.get("error_type", "ProbeError"),
                message=item.get("error", "probe execution failed"),
            )
            error.text = item.get("traceback", "")
    ET.indent(suites)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suites).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--junit", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    started = time.perf_counter()
    delivery = _run_delivery()
    extensions = _run_extensions()
    source_paths = (
        "src/cpswm/data_preflight/simulator_capture.py",
        "src/cpswm/data_preflight/train_coverage.py",
        "src/cpswm/data_preflight/visible_prefix.py",
        "tests/test_structure_two_data_preflight.py",
        "tests/test_d0_shift_scenarios.py",
        "tools/structure_two_data_preflight.py",
    )
    payload = {
        "schema": "cpswm.pc-b.b7-independent-audit@1",
        "delivery_sha": "6e07ab682a9ec15e959e1a50001e237877bc4773",
        "actual_code_sha": "57e8576c7dd48203839cdd0ae3a4cdb295db7185",
        "scope": {
            "training_run": False,
            "method_arm_run": False,
            "reserved_validation_or_confirmation_read": False,
            "reserved_validation_or_confirmation_generated": False,
            "real_simulator_run": False,
        },
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "executable": sys.executable,
            "cpu_count": os.cpu_count(),
            "cwd": str(ROOT),
            "pytest_installed": False,
            "execution_mode": "direct invocation of exact test functions with minimal assertion shim",
        },
        "source_sha256": {path: _sha256(ROOT / path) for path in source_paths},
        "delivery_matrix": delivery,
        "extensions": extensions,
        "summary": {
            "delivery_passed": sum(item["status"] == "passed" for item in delivery),
            "delivery_failed": sum(item["status"] != "passed" for item in delivery),
            "extension_defenses_passed": sum(
                item["status"] == "defense_passed" for item in extensions
            ),
            "extension_vulnerabilities": sum(item["status"] == "vulnerable" for item in extensions),
            "extension_probe_errors": sum(item["status"] == "probe_error" for item in extensions),
            "seconds": time.perf_counter() - started,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
    if args.junit is not None:
        if args.junit.exists():
            parser.error("junit output already exists")
        _write_junit(args.junit, delivery, extensions)
    print(json.dumps(payload["summary"], sort_keys=True))
    print(args.output)
    return (
        1
        if payload["summary"]["delivery_failed"]
        or payload["summary"]["extension_vulnerabilities"]
        or payload["summary"]["extension_probe_errors"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
