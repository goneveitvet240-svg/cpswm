"""Actual consumers, fully resealed boundary violations and full-CLI fairness forgeries."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from structure_two_comparison_audit_adversary import load_analyzer
from test_structure_two_comparison_audit_verification import BUNDLE, cli

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
from cpswm.system.evaluation_operations import structure_two_comparison_fairness as fair
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def setup():
    dataset = (
        audit.D0SyntheticReplayExperimentConfig.load(ROOT / audit.DATA_CONFIG)
        .build_adapter()
        .build()
    )
    train = audit.base._learned_training_material(dataset)
    model = audit.base._fit_learned_model(
        train, {"base_width": 8, "learning_rate": 0.05, "l2": 0.0}
    )
    ep = dataset.visible_episodes(Split.TEST)[0]
    states = audit.make_states(ep, model, train, 1.0, 0.2)
    step = ep.steps[0]
    packet = audit.base._packet_for_step(
        ep, step, schedule_commitment_sha256=audit.base._episode_schedule_commitment(ep)
    )
    receipts = [s.consume_matched_ciav_packet(packet, step, step_index=0) for s in states]
    posteriors = [s.predict_location_posteriors(packet) for s in states]
    return dataset, train, model, ep, step, packet, receipts, posteriors


def test_actual_boundaries_accept_legitimate_inputs_and_decodes(setup):
    _, _, _, _, step, packet, receipts, ps = setup
    fair.check_step(packet, step, ps, receipts)
    for p in ps:
        a = audit.decode(p, step, 0, content_uuid(audit.AUDIT_ID, "fairness-test"))
        fair.check_decoded(p, a, step)


@pytest.mark.parametrize("attack", ["support", "visible", "arm", "resources", "packet"])
def test_resealed_boundary_attacks_rejected(setup, attack):
    _, _, _, _, step, packet, receipts, ps = setup
    ps, receipts = list(ps), list(receipts)
    if attack in {"support", "visible", "arm"}:
        raw = ps[-1].model_dump(mode="json", exclude={"posterior_sha256"})
        if attack == "support":
            raw["location_support"].reverse()
        if attack == "visible":
            raw["source_visible_step_sha256"] = "b" * 64
        if attack == "arm":
            raw["arm"] = ps[0].arm.value
        ps[-1] = type(ps[-1])(**raw, posterior_sha256=content_sha256(raw))
    else:
        # All arms agree, and every receipt hash is recomputed. Old matched check accepts.
        changed = []
        for r in receipts:
            raw = r.model_dump(mode="json", exclude={"receipt_sha256"})
            raw["time_cost" if attack == "resources" else "packet_sha256"] = (
                1.0 if attack == "resources" else "b" * 64
            )
            changed.append(type(r)(**raw, receipt_sha256=content_sha256(raw)))
        receipts = changed
        audit.base.verify_matched_consumption(receipts)
    with pytest.raises(ValueError, match="FAIRNESS_"):
        fair.check_step(packet, step, ps, receipts)


@pytest.mark.parametrize("attack", ["search", "put_back", "identity"])
def test_actual_decoded_output_mutations_rejected(setup, attack):
    _, _, _, _, step, _, _, ps = setup
    p = ps[0]
    a = audit.decode(p, step, 0, content_uuid(audit.AUDIT_ID, "fairness-test"))
    target = next(x for x in p.location_support if x != a.search_plan[0].location_id)
    mass = {x: float(x == target) for x in p.location_support}
    if attack == "search":
        changed = audit.with_distributions(p, current=mass)
    elif attack == "put_back":
        target = next(x for x in p.location_support if x != a.put_back_action.location_id)
        changed = audit.with_distributions(
            p, habit={x: float(x == target) for x in p.location_support}
        )
    else:
        raw = p.model_dump(mode="json", exclude={"posterior_sha256"})
        raw["step_id"] = str(content_uuid(audit.AUDIT_ID, "wrong"))
        changed = type(p)(**raw, posterior_sha256=content_sha256(raw))
    a = audit.decode(changed, step, 0, content_uuid(audit.AUDIT_ID, "fairness-test"))
    with pytest.raises(ValueError, match="FAIRNESS_"):
        fair.check_decoded(p, a, step)


@pytest.mark.parametrize("stage", list(Split))
def test_real_split_access_positive_and_foreign_truth_rejection(setup, stage):
    dataset, *_ = setup
    access = fair.SplitAccess(dataset, stage)
    assert access.visible_episodes(stage)
    other = next(s for s in Split if s != stage)
    with pytest.raises(ValueError, match="FAIRNESS_SPLIT_ACCESS"):
        access.visible_episodes(other)
    with pytest.raises(ValueError, match="FAIRNESS_TRUTH_SPLIT"):
        access.truth_for(dataset.visible_episodes(other)[0].episode_id)
    if stage == Split.TRAIN:
        assert access.truth_for(dataset.visible_episodes(stage)[0].episode_id)
    else:
        with pytest.raises(ValueError, match="FAIRNESS_EARLY_TRUTH"):
            access.truth_for(dataset.visible_episodes(stage)[0].episode_id)


def test_old_validation_consumer_rejected_new_consumer_matches_real_scores(setup):
    dataset, _, _, *_ = setup
    ep = dataset.visible_episodes(Split.VALIDATION)[0]
    access = fair.SplitAccess(dataset, Split.VALIDATION)
    with pytest.raises(ValueError, match="FAIRNESS_EARLY_TRUTH"):
        audit.base._evaluate_single_state(
            access, ep, audit.base.AMGLocationAdapter(ep, parameter=0.2)
        )
    expected = audit.base._evaluate_single_state(
        dataset, ep, audit.base.AMGLocationAdapter(ep, parameter=0.2)
    )
    actual = fair.validation_errors(access, ep, audit.base.AMGLocationAdapter(ep, parameter=0.2))
    assert actual == (expected.search_error_rate, expected.put_back_error_rate)
    assert len(access.events) == len(ep.steps)
    assert all(e["kind"] == "score_after_commit" for e in access.events)


def test_safe_selection_preserves_frozen_grid_and_results(setup):
    dataset, material, _, *_ = setup
    config = copy.deepcopy(audit.base._load_config(ROOT))
    config["learned_two_stage"].update(
        base_widths=[8], learning_rates=[0.05], l2_values=[0.0], location_smoothing_values=[1.0]
    )
    config["amg"]["parameter_values"] = [0.2]
    old = audit.base._validation_selection(dataset, config, material)
    fresh = fair.validation_selection(dataset, config, material)
    assert old[0] == fresh[0]
    assert old[2:] == fresh[2:4]
    assert fresh[-1]["model_fits"]
    with pytest.raises(ValueError, match="FAIRNESS_TRAINING_IDS"):
        fair.validation_selection(dataset, config, replace(material, training_episode_ids=()))


def test_consumer_probe_records_actual_values_and_restores_tracer(setup):
    dataset, train, model, ep, *_ = setup
    probe = fair.ConsumerProbe()
    with probe:
        rows, _ = audit.evaluate_episode(dataset, ep, audit.make_states(ep, model, train, 1.0, 0.2))
    result = probe.result()
    assert any(r.get("feature_values") for r in result["returns"])
    assert any(r.get("evidence") for r in result["returns"])
    assert any(r.get("actor_likelihoods") for r in result["returns"])
    assert result["executed_attribute_reads"]["_feature_row:actor_posterior"] > 0
    assert not any(
        k.startswith("_feature_row:ordered_role") for k in result["executed_attribute_reads"]
    )
    assert fair.findings(rows)["comparison_fairness"] == "NOT_ESTABLISHED"


def test_complete_fairness_forgeries_real_cli_and_valid_positive(tmp_path):
    snapshot = audit.load_bundle(BUNDLE)
    evidence = Path(os.environ.get("S2_FAIRNESS_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    args = ["--bundle", BUNDLE]
    attacks = []
    for case in (
        "future_support",
        "missing_owner",
        "costs",
        "selection_access",
        "consumer_features",
        "fairness_claim",
    ):
        p, rows = copy.deepcopy(snapshot.payload), copy.deepcopy(snapshot.rows)
        if case == "future_support":
            for r in rows:
                r["future_support_count"] = 0
        elif case == "missing_owner":
            for r in rows:
                r["fairness_step"]["amg_owner_missing"] = False
        elif case == "costs":
            for r in rows:
                for costs in r["fairness_step"]["costs"].values():
                    costs["time_cost"] = 1.0
        elif case == "selection_access":
            p["fairness_execution"]["selection"]["access_events"] = []
        elif case == "consumer_features":
            for r in p["fairness_execution"]["consumer_probe"]["returns"]:
                if "feature_values" in r:
                    r["feature_values"] = [0.0] * len(r["feature_values"])
        p["fairness"] = fair.findings(rows)
        if case == "fairness_claim":
            p["fairness"]["comparison_fairness"] = "PASSED"
        p["summary"] = audit.aggregate(rows)
        p["semantic_steps_sha256"] = content_sha256(audit._semantic_rows(rows))
        dest = tmp_path / case
        audit.save(dest, p, rows, {})
        (dest / "attribution.json").write_text(json.dumps(load_analyzer(ROOT).analyze(dest, ROOT)))
        args += ["--bundle", dest]
        attacks.append(case)
    result = cli(*args, "--verify")
    (evidence / "fairness_forgery_cli.log").write_text(result.stdout + result.stderr)
    out = json.loads(result.stdout.splitlines()[-1])
    (evidence / "fairness_forgery_matrix.json").write_text(
        json.dumps({"cases": attacks, "exit_code": result.returncode, "result": out}, indent=2)
    )
    assert result.returncode == 1
    assert out["fresh_replay_performed"]
    assert out["results"][0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    for record in out["results"][1:]:
        assert record["status"] == "REJECTED"
        assert (
            "FRESH_REPLAY_STEP_MISMATCH" in record["error"]
            or "fresh diagnostic differs at audit.fairness" in record["error"]
        )
