"""Independent mathematical and binding audit for B6 frozen code.

This does not modify or monkeypatch production code.  Expected mathematical
properties are calculated independently of the implementation under test.
Confirmed boundary gaps are emitted as findings and as JUnit failures so they
cannot be mistaken for a fully green acceptance run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FROZEN_SHA = "1d24099a025c9d7c00a59e4c78c593703924b0eb"


def git_blob(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


def source_identity() -> dict[str, object]:
    tree = json.loads((ROOT / "REMOTE_TREE_MANIFEST.json").read_text())["tree"]
    expected = {row["path"]: row["sha"] for row in tree if row["type"] == "blob"}
    actual = {
        str(path.relative_to(ROOT)): git_blob(path)
        for path in sorted((ROOT / "src").rglob("*.py"))
    }
    mismatch = {
        name: {"expected": expected.get(name), "actual": value}
        for name, value in actual.items()
        if expected.get(name) != value
    }
    return {"checked": len(actual), "matched": len(actual) - len(mismatch), "mismatch": mismatch}


def setup_imports():
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]
    import b6_pytest_shim as shim

    sys.modules["pytest"] = shim


def conditional_oracle() -> dict[str, object]:
    # The frozen tests establish this import order.  A separate cold-start case
    # below checks whether the public component works without that hidden setup.
    importlib.import_module("test_structure_two_formal_revision_lineage")
    from cpswm.system.structure_two_conditional_updates import (
        ConditionalMeasurement,
        rebuild_conditional_state,
    )
    from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

    errors = []
    for seed in range(25):
        rng = np.random.default_rng(seed)
        dim, locations, observations = 3, 4, 2
        base_a = rng.normal(size=(dim, dim))
        base_i = rng.normal(size=(dim, dim))
        a = base_a.T @ base_a + np.eye(dim)
        information = base_i.T @ base_i + np.eye(dim)
        alpha = rng.random(locations) + 0.1
        b = rng.normal(size=dim)
        natural = rng.normal(size=dim)
        prior = ConditionalAnalyticState(
            tuple(UUID(int=1000 + index) for index in range(locations)),
            tuple(alpha),
            tuple(tuple(row) for row in a),
            tuple(b),
            tuple(tuple(row) for row in information),
            tuple(natural),
        )
        x = rng.normal(size=dim)
        z = rng.normal(size=observations)
        h = rng.normal(size=(observations, dim))
        raw_cov = rng.normal(size=(observations, observations))
        covariance = raw_cov.T @ raw_cov + np.eye(observations) * 0.5
        mass = rng.random(locations)
        rls_weight = float(rng.random())
        information_weight = float(rng.random())
        target = float(rng.normal())
        item = ConditionalMeasurement(
            evidence_cluster_id=UUID(int=2000 + seed),
            source_record_ids=(UUID(int=3000 + seed),),
            observation_model_id=f"independent-oracle-{seed}",
            location_mass=tuple(mass),
            rls_features=tuple(x),
            rls_target=target,
            rls_weight=rls_weight,
            measurement=tuple(z),
            observation_matrix=tuple(tuple(row) for row in h),
            noise_covariance=tuple(tuple(row) for row in covariance),
            information_weight=information_weight,
        )
        result = rebuild_conditional_state(prior, (item,))
        expected = (
            alpha + mass,
            a + rls_weight * np.outer(x, x),
            b + rls_weight * x * target,
            information + information_weight * h.T @ np.linalg.solve(covariance, h),
            natural + information_weight * h.T @ np.linalg.solve(covariance, z),
        )
        actual = (result.alpha, result.a, result.b, result.information, result.information_vector)
        if not all(np.allclose(got, want, rtol=1e-12, atol=1e-12) for got, want in zip(actual, expected)):
            errors.append(seed)

    base = ConditionalAnalyticState(
        (UUID(int=1), UUID(int=2)),
        (1.0, 1.0),
        ((2.0, 0.0), (0.0, 2.0)),
        (0.0, 0.0),
        ((1.0, 0.0), (0.0, 1.0)),
        (0.0, 0.0),
    )

    def measurement(cluster: int, target: float, model: str, source: int):
        return ConditionalMeasurement(
            evidence_cluster_id=UUID(int=cluster),
            source_record_ids=(UUID(int=source),),
            observation_model_id=model,
            location_mass=(0.25, 0.75),
            rls_features=(1.0, 2.0),
            rls_target=target,
            rls_weight=0.5,
            measurement=(target,),
            observation_matrix=((1.0, 2.0),),
            noise_covariance=((2.0,),),
            information_weight=0.5,
        )

    first, second = measurement(10, 4.0, "m1", 20), measurement(11, 8.0, "m2", 21)
    parent = rebuild_conditional_state(base, (first,))
    accumulated = rebuild_conditional_state(parent, (second,))
    direct = rebuild_conditional_state(base, (first, second))
    corrected = rebuild_conditional_state(base, (replace(first, measurement=(6.0,)), second))
    restored = rebuild_conditional_state(base, (first,))
    lifecycle_ok = accumulated == direct and restored == parent and corrected != direct

    invalid_rejections = 0
    invalids = (
        replace(first, noise_covariance=((0.0,),)),
        replace(first, noise_covariance=((1.0, 0.1), (0.0, 1.0))),
        replace(first, observation_matrix=((1.0,),)),
        replace(first, information_weight=float("nan")),
        replace(first, rls_target=float("inf")),
    )
    for item in invalids:
        try:
            rebuild_conditional_state(base, (item,))
        except ValueError:
            invalid_rejections += 1
    try:
        rebuild_conditional_state(base, (first, first))
    except ValueError:
        invalid_rejections += 1

    alias_one = rebuild_conditional_state(base, (first,))
    alias_two = rebuild_conditional_state(
        base,
        (replace(first, source_record_ids=(UUID(int=999),), observation_model_id="foreign-model"),),
    )
    return {
        "random_trials": 25,
        "random_mismatches": errors,
        "lifecycle_ok": lifecycle_ok,
        "invalid_rejections": invalid_rejections,
        "invalid_total": len(invalids) + 1,
        "source_model_alias_same_reference": alias_one.reference == alias_two.reference,
        "source_model_alias_note": (
            "ConditionalAnalyticState intentionally retains numeric blocks and cluster IDs only; "
            "source_record_ids and observation_model_id are not bound into its reference."
        ),
    }


def cold_entrypoint_imports() -> dict[str, object]:
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    commands = {
        "module_only": "import cpswm.system.structure_two_conditional_updates",
        "required_prior_type": (
            "from cpswm.system.structure_two_particle_workspace "
            "import ConditionalAnalyticState"
        ),
        "first_public_call": (
            "from cpswm.system.structure_two_conditional_updates import "
            "rebuild_conditional_state; rebuild_conditional_state(None, ())"
        ),
        "joint_view_first_digest": (
            "from uuid import uuid4; "
            "from cpswm.system.structure_two_joint_consumption import JointDecisionView; "
            "view=JointDecisionView(uuid4(),uuid4(),uuid4(),(),1.0); "
            "print(view.content_sha256)"
        ),
    }
    results = {}
    for name, source in commands.items():
        completed = subprocess.run(
            [sys.executable, "-c", source],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        results[name] = {
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "circular_import": "partially initialized module" in completed.stderr,
        }
    return {
        "results": results,
        "module_import_succeeds_but_public_dependency_fails_circularly": (
            results["module_only"]["returncode"] == 0
            and results["required_prior_type"]["circular_import"]
            and results["first_public_call"]["circular_import"]
            and results["joint_view_first_digest"]["circular_import"]
        ),
    }


def entropy(probabilities) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0.0)


def manual_expected_value(prior, likelihoods, utilities) -> tuple[float, float]:
    baseline = max(sum(prior[a] * row[a] for a in prior) for row in utilities.values())
    expected = 0.0
    for outcome in likelihoods:
        p_outcome = sum(prior[a] * likelihoods[outcome][a] for a in prior)
        if p_outcome == 0.0:
            continue
        posterior = {a: prior[a] * likelihoods[outcome][a] / p_outcome for a in prior}
        expected += p_outcome * max(
            sum(posterior[a] * row[a] for a in posterior) for row in utilities.values()
        )
    return baseline, expected


def joint_oracle_and_status() -> dict[str, object]:
    from cpswm.contracts.grounded_search import ObservationActionCandidate
    from cpswm.world_model.grounded_search.active_verification import (
        CauseInformationActiveVerificationPlanner,
        JointParticleVerificationBelief,
        VerificationCause,
    )

    atoms = tuple(UUID(int=100 + index) for index in range(5))
    causes = {a: VerificationCause.HABIT if index < 4 else VerificationCause.UNRESOLVED for index, a in enumerate(atoms)}
    probabilities = {
        "correlated": (0.4, 0.0, 0.0, 0.4, 0.2),
        "independent": (0.2, 0.2, 0.2, 0.2, 0.2),
    }
    likelihoods = {
        "role0": dict(zip(atoms, (1.0, 1.0, 0.0, 0.0, 0.5), strict=True)),
        "role1": dict(zip(atoms, (0.0, 0.0, 1.0, 1.0, 0.5), strict=True)),
    }
    utilities = {
        UUID(int=200): dict(zip(atoms, (1.0, 0.0, 1.0, 0.0, 0.5), strict=True)),
        UUID(int=201): dict(zip(atoms, (0.0, 1.0, 0.0, 1.0, 0.5), strict=True)),
    }
    consolidation = {UUID(int=202): dict.fromkeys(atoms, 0.0)}
    action = ObservationActionCandidate(
        action_type="micro_verify",
        label="independent joint oracle",
        observation_likelihood_model_id="independent-role-model",
        calibration_domain="audit",
        outcome_likelihoods=likelihoods,
        motion_cost=0.0,
        time_cost=0.1,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    observations = {}
    plans = {}
    for label, values in probabilities.items():
        prior = dict(zip(atoms, values, strict=True))
        belief = JointParticleVerificationBelief(
            posterior=prior,
            cause_by_atom=causes,
            source_snapshot_sha256=("a" if label == "correlated" else "b") * 64,
        )
        plan = CauseInformationActiveVerificationPlanner().select(
            belief,
            (action,),
            terminal_decision_utilities=utilities,
            consolidation_decision_utilities=consolidation,
            privacy_budget=1.0,
        )
        baseline, expected = manual_expected_value(prior, likelihoods, utilities)
        prior_joint = entropy(prior.values())
        expected_joint = 0.0
        for outcome, row in likelihoods.items():
            p_outcome = sum(prior[a] * row[a] for a in atoms)
            posterior = [prior[a] * row[a] / p_outcome for a in atoms] if p_outcome else []
            expected_joint += p_outcome * entropy(posterior)
        observations[label] = {
            "manual_evsi": expected - baseline,
            "planner_evsi": plan.scores[0].expected_utility_gain,
            "planner_cause_information_gain": plan.scores[0].expected_cause_information_gain,
            "manual_joint_information_gain": prior_joint - expected_joint,
            "net": plan.scores[0].net_value,
            "should_act": plan.should_act,
        }
        plans[label] = plan

    unresolved_only = JointParticleVerificationBelief(
        posterior={UUID(int=999): 1.0},
        cause_by_atom={UUID(int=999): VerificationCause.UNRESOLVED},
        source_snapshot_sha256="c" * 64,
    )
    rows = {UUID(int=998): {UUID(int=999): 0.0}}
    no_actions = CauseInformationActiveVerificationPlanner().select(
        unresolved_only,
        (),
        terminal_decision_utilities=rows,
        consolidation_decision_utilities=rows,
        privacy_budget=1.0,
    )
    empty_rejected = False
    try:
        JointParticleVerificationBelief(
            posterior={}, cause_by_atom={}, source_snapshot_sha256="d" * 64
        )
    except ValueError:
        empty_rejected = True
    return {
        "identical_cause_marginal": True,
        "observations": observations,
        "expected_relation": observations["correlated"]["manual_evsi"] > observations["independent"]["manual_evsi"],
        "empty_belief_rejected": empty_rejected,
        "unresolved_only_no_action": not no_actions.should_act,
        "empty_actions_stop_reason": no_actions.stop_reason,
        "empty_actions_misclassified_as_privacy": no_actions.stop_reason == "privacy_hard_constraint_blocked_all_actions",
    }


def binding_attacks() -> dict[str, object]:
    from cpswm.contracts.grounded_search import ObservationActionCandidate
    from cpswm.system.structure_two_joint_consumption import JointDecisionView
    from cpswm.world_model.grounded_search.active_verification import (
        CauseInformationActiveVerificationPlanner,
    )

    old = importlib.import_module("test_structure_two_formal_revision_lineage")
    projection = importlib.import_module("test_structure_two_w3_native_posterior_projection")
    core = old._legacy_history(1).system.core
    batch = core.stage_prepared_particle_candidates(**projection.projected(core))
    runtime_id = core._particle_workspace.runtime_id
    records = core._particle_workspace.records
    legal = JointDecisionView.from_batch(
        runtime_id=runtime_id,
        expected_snapshot_id=core.current_snapshot.snapshot_id,
        batch=batch,
        records=records,
    )
    foreign_runtime = uuid4()
    foreign_runtime_accepted = False
    try:
        foreign = JointDecisionView.from_batch(
            runtime_id=foreign_runtime,
            expected_snapshot_id=core.current_snapshot.snapshot_id,
            batch=batch,
            records=records,
        )
        foreign_runtime_accepted = foreign.runtime_id == foreign_runtime
    except ValueError:
        pass

    positive_id = legal.atoms[0].particle_id
    tampered_records = dict(records)
    tampered_records[positive_id] = replace(
        tampered_records[positive_id], source_frame_sha256="0" * 64
    )
    source_hash_accepted = False
    try:
        tampered = JointDecisionView.from_batch(
            runtime_id=runtime_id,
            expected_snapshot_id=core.current_snapshot.snapshot_id,
            batch=batch,
            records=tampered_records,
        )
        source_hash_accepted = next(
            atom for atom in tampered.atoms if atom.particle_id == positive_id
        ).source_frame_sha256 == "0" * 64
    except ValueError:
        pass

    belief = legal.verification_belief()
    atom_ids = belief.posterior
    utilities = {UUID(int=700): dict.fromkeys(atom_ids, 0.0)}
    action = ObservationActionCandidate(
        action_type="micro_verify",
        label="digest invariance audit",
        observation_likelihood_model_id="audit-model",
        calibration_domain="audit",
        outcome_likelihoods={
            "yes": dict.fromkeys(atom_ids, 0.5),
            "no": dict.fromkeys(atom_ids, 0.5),
        },
        motion_cost=0.0,
        time_cost=0.0,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    planner = CauseInformationActiveVerificationPlanner()
    first = planner.select(
        belief,
        (action,),
        terminal_decision_utilities=utilities,
        consolidation_decision_utilities=utilities,
        privacy_budget=1.0,
    )
    changed_digest = belief.model_copy(update={"source_snapshot_sha256": "f" * 64})
    second = planner.select(
        changed_digest,
        (action,),
        terminal_decision_utilities=utilities,
        consolidation_decision_utilities=utilities,
        privacy_budget=1.0,
    )
    digest_unused = first == second

    missing_particle_rejected = False
    missing = dict(records)
    missing.pop(positive_id)
    try:
        JointDecisionView.from_batch(
            runtime_id=runtime_id,
            expected_snapshot_id=core.current_snapshot.snapshot_id,
            batch=batch,
            records=missing,
        )
    except ValueError:
        missing_particle_rejected = True

    return {
        "legal_atom_count": len(legal.atoms),
        "legal_unresolved_probability": legal.unresolved_probability,
        "missing_particle_rejected": missing_particle_rejected,
        "foreign_runtime_id_accepted": foreign_runtime_accepted,
        "tampered_source_frame_hash_accepted": source_hash_accepted,
        "belief_source_digest_unused_by_planner": digest_unused,
    }


def default_path_inventory() -> dict[str, object]:
    names = ("JointDecisionView", "rebuild_conditional_state")
    references = {name: [] for name in names}
    for path in sorted((ROOT / "src").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        for name in names:
            if name in text and not relative.endswith(
                ("structure_two_joint_consumption.py", "structure_two_conditional_updates.py")
            ):
                references[name].append(relative)
    return {
        "production_references_outside_component_modules": references,
        "default_production_path_connected": any(references.values()),
        "prepared_seam_exercised": True,
    }


def run_case(name, function):
    started = time.perf_counter()
    try:
        detail = function()
        return {"case": name, "status": "observed", "seconds": time.perf_counter() - started, "detail": detail}
    except BaseException as error:
        return {
            "case": name,
            "status": "runner_error",
            "seconds": time.perf_counter() - started,
            "exception": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    setup_imports()
    started = time.perf_counter()
    cases = [
        run_case("cold_public_entrypoint_import_order", cold_entrypoint_imports),
        run_case("independent_conditional_block_oracle", conditional_oracle),
        run_case("joint_distribution_and_unknown_mass_oracle", joint_oracle_and_status),
        run_case("source_particle_statistics_action_binding_attacks", binding_attacks),
        run_case("prepared_seam_vs_default_path_inventory", default_path_inventory),
    ]
    seconds = time.perf_counter() - started
    runner_errors = [row for row in cases if row["status"] == "runner_error"]
    details = {row["case"]: row.get("detail", {}) for row in cases}
    findings = [
        {
            "id": "B6-F1",
            "severity": "high-if-promoted-to-production-authority",
            "title": "JointDecisionView accepts a caller-selected foreign runtime and an unverified source-frame hash",
            "confirmed": bool(
                details.get("source_particle_statistics_action_binding_attacks", {}).get("foreign_runtime_id_accepted")
                and details.get("source_particle_statistics_action_binding_attacks", {}).get("tampered_source_frame_hash_accepted")
            ),
            "scope": "Declared value-object seam; becomes a security/correctness bug if treated as a trusted production view.",
        },
        {
            "id": "B6-F2",
            "severity": "medium",
            "title": "Joint belief source_snapshot_sha256 is not consumed by the planner",
            "confirmed": bool(
                details.get("source_particle_statistics_action_binding_attacks", {}).get("belief_source_digest_unused_by_planner")
            ),
            "scope": "Action likelihood and utility provenance cannot be enforced by the planner API itself.",
        },
        {
            "id": "B6-F3",
            "severity": "low",
            "title": "An empty action set is reported as privacy-blocked",
            "confirmed": bool(
                details.get("joint_distribution_and_unknown_mass_oracle", {}).get("empty_actions_misclassified_as_privacy")
            ),
            "scope": "Misleading stop/audit reason; selection remains no-action.",
        },
        {
            "id": "B6-F4",
            "severity": "high",
            "title": "Both new components' cold public operations fail through a circular import",
            "confirmed": bool(
                details.get("cold_public_entrypoint_import_order", {}).get(
                    "module_import_succeeds_but_public_dependency_fails_circularly"
                )
            ),
            "scope": (
                "The module-only regression is green, but the conditional first call, its required "
                "prior type import, and JointDecisionView.content_sha256 fail in a fresh interpreter."
            ),
        },
    ]
    identity = source_identity()
    record = {
        "frozen_code_sha": FROZEN_SHA,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(ROOT),
        "command": sys.argv,
        "source_identity": identity,
        "seconds": seconds,
        "cases": cases,
        "findings": findings,
    }
    (args.output_dir / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    suite = ET.Element(
        "testsuite",
        name="B6 independent adversarial audit",
        tests=str(len(cases) + len(findings)),
        failures=str(len(runner_errors) + sum(item["confirmed"] for item in findings)),
        errors="0",
        skipped="0",
        time=f"{seconds:.9f}",
    )
    for row in cases:
        node = ET.SubElement(
            suite,
            "testcase",
            classname="b6.audit",
            name=str(row["case"]),
            time=f"{float(row['seconds']):.9f}",
        )
        if row["status"] == "runner_error":
            failure = ET.SubElement(node, "failure", type="runner_error", message=str(row.get("message", "")))
            failure.text = str(row.get("traceback", ""))
    for finding in findings:
        node = ET.SubElement(
            suite,
            "testcase",
            classname="b6.finding",
            name=str(finding["id"]),
            time="0",
        )
        if finding["confirmed"]:
            failure = ET.SubElement(
                node,
                "failure",
                type=str(finding["severity"]),
                message=str(finding["title"]),
            )
            failure.text = str(finding["scope"])
    ET.ElementTree(suite).write(args.output_dir / "junit.xml", encoding="utf-8", xml_declaration=True)
    summary = {
        "runner_errors": len(runner_errors),
        "confirmed_findings": sum(item["confirmed"] for item in findings),
        "source_identity": identity,
        "seconds": seconds,
    }
    print(json.dumps(summary))
    return int(bool(runner_errors or identity["mismatch"] or any(item["confirmed"] for item in findings)))


if __name__ == "__main__":
    raise SystemExit(main())
