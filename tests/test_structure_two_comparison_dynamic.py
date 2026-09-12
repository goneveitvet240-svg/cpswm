"""Real production challenges; empty invocation or hash change cannot pass coverage."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from structure_two_comparison_audit_adversary import load_analyzer
from test_structure_two_comparison_audit_verification import BUNDLE, cli

from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
from cpswm.system.evaluation_operations import structure_two_comparison_dynamic as dynamic
from cpswm.system.evaluation_operations import structure_two_comparison_fairness as fair
from cpswm.system.reproducibility import content_sha256, content_uuid

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def inputs():
    dataset = (
        audit.D0SyntheticReplayExperimentConfig.load(ROOT / audit.DATA_CONFIG)
        .build_adapter()
        .build()
    )
    episode = dataset.visible_episodes(audit.ProjectTwoDatasetSplit.TEST)[0]
    material = audit.base._learned_training_material(
        fair.SplitAccess(dataset, audit.ProjectTwoDatasetSplit.TRAIN)
    )
    model = audit.base._fit_learned_model(
        material, {"base_width": 8, "learning_rate": 0.05, "l2": 0.0}
    )
    return episode, model, material, 1.0, 0.2


@pytest.fixture(scope="module")
def results(inputs):
    return dynamic.run_scenes(*inputs)


def test_predeclared_legal_scenarios_and_common_horizon(inputs):
    episode = inputs[0]
    lengths = set()
    for plan in dynamic.PLANS:
        assert all(plan[k] for k in ("path", "change", "invariant", "necessary"))
        ep = dynamic.fixture(episode, plan)
        assert type(ep).model_validate(ep.model_dump()) == ep
        assert ep.dataset_version.endswith("development-only")
        assert ep.split == audit.ProjectTwoDatasetSplit.TRAIN
        assert ep.known_location_ids
        lengths.add(len(ep.steps))
    assert len(lengths) == 1


@pytest.mark.parametrize("counts", [(0, 1, 1), (1, 0, 1), (1, 1, 0), (0, 0, 0)])
def test_nonempty_guard_rejects_vacuous_coverage(counts):
    assert (
        dynamic.coverage_status(
            committed=counts[0], action_differences=counts[1], executed=counts[2]
        )
        == dynamic.MISSING
    )


def test_nonempty_guard_has_legal_positive_and_rejects_negative_counts():
    assert (
        dynamic.coverage_status(committed=1, action_differences=1, executed=1)
        == "NONEMPTY_LOCAL_COVERAGE"
    )
    with pytest.raises(ValueError, match="negative coverage"):
        dynamic.coverage_status(committed=-1, action_differences=1, executed=1)


def test_real_long_term_positive_is_not_misattributed_to_direct_p5(results):
    stable = results["scenes"][0]
    assert stable["max_ordinary_reference_committed"] > 0
    assert stable["max_direct_p5_committed"] == 0
    assert stable["complete_mechanism"] == dynamic.MISSING
    assert all(s["complete_mechanism"] == dynamic.MISSING for s in results["scenes"])
    assert results["scientific_acceptance"] is False


def test_actual_regime_creation_and_reactivation_reference(results):
    scene = next(s for s in results["scenes"] if s["plan"]["id"] == "habit_change_return")
    regimes = [
        r["ordinary_reference_same_visible_input"]["after"]["active_regime"] for r in scene["rows"]
    ]
    assert regimes[0] == regimes[-1]
    assert any(r != regimes[0] for r in regimes)


def test_actual_same_different_negative_ciav_paths(results):
    probes = results["ciav_interface_probes"]
    assert probes["same"]["closure"] == "same_location_fast_verification"
    assert probes["different"]["closure"] == "full_transition"
    assert probes["negative"]["detection_outcome"] == "not_observed"
    assert all(p["all_seven_invoked"] for p in probes.values())


def test_real_feedback_nonempty_mass_and_duplicate_invariant(results):
    success = results["feedback_interface_probes"]["success"]
    negative = results["feedback_interface_probes"]["not_found"]
    assert success["status"] == negative["status"] == "RETURNED"
    assert success["long_term_mass_delta"] > 0
    assert success["duplicate_unchanged"] and negative["duplicate_unchanged"]
    assert success["presence_posterior"] > negative["presence_posterior"]
    assert results["execution"]["status"] == dynamic.MISSING


def test_similar_instance_cannot_be_accepted_as_valid_comparison(results):
    scene = next(s for s in results["scenes"] if s["plan"]["id"] == "similar_instance")
    last = scene["rows"][-1]
    assert last["contract_check"] != "PASS"
    assert all(v["status"] == "REJECTED" for v in last["arms"].values())
    assert all("object" in v["error"] or "target" in v["error"] for v in last["arms"].values())


def test_target_checker_legal_and_fully_resealed_wrong_instance(inputs):
    episode, model, material, smoothing, parameter = inputs
    step = episode.steps[0]
    packet = audit.base._packet_for_step(
        episode, step, schedule_commitment_sha256=audit.base._episode_schedule_commitment(episode)
    )
    state = audit.make_states(episode, model, material, smoothing, parameter)[1]
    state.consume_matched_ciav_packet(packet, step, step_index=0)
    p = state.predict_location_posteriors(packet)
    action = audit.decode(p, step, 0, content_uuid(dynamic.ID, "target-test"))
    fair.check_decoded(p, action, step)
    raw = p.model_dump(mode="json", exclude={"posterior_sha256"})
    raw["target_object_id"] = str(content_uuid(dynamic.ID, "different-instance"))
    forged = type(p)(**raw, posterior_sha256=content_sha256(raw))
    action = audit.decode(forged, step, 0, content_uuid(dynamic.ID, "target-test"))
    with pytest.raises(ValueError, match="FAIRNESS_TARGET_INSTANCE"):
        fair.check_decoded(forged, action, step)


def test_controlled_intervention_measures_actions_and_posterior(results):
    rows = results["controlled_contrasts"]
    assert rows and all(r["arms"] for r in rows)
    # All scenarios have identical causal evidence until the planned change.
    for row in rows:
        if row["step_index"] < 6:
            assert all(v["habit_total_variation"] == 0 for v in row["arms"].values())
    assert any(v["habit_total_variation"] > 0 for r in rows for v in r["arms"].values())


def test_current_production_revision_defect_is_not_promoted_to_success(results):
    correct = results["production_boundary_probes"]["correct"]
    assert correct["nonempty_target"]
    assert correct["operations"] == ["correct"]
    assert not correct["old_committed"] and not correct["new_committed"]
    assert not correct["new_quarantined"]
    assert correct["repeat_semantic_unchanged"]
    retract = results["production_boundary_probes"]["retract"]
    assert retract["after"]["committed"] < retract["before"]["committed"]


def test_frozen_final_pct_is_not_reopened():
    result = dynamic.contract_matrix(ROOT)
    assert (
        result["final_frozen_protocol"]["primary_utility"]["metric"] == "penalized_completion_time"
    )
    assert not result["final_frozen_protocol"]["applied_to_this_development_experiment"]
    assert not result["scientific_fairness_established"]


def test_dynamic_actual_output_survives_strict_json_retention(results):
    retained = json.loads(json.dumps(results))
    assert audit.first_difference(retained, results) is None


def test_dynamic_fresh_semantic_replay_matches(inputs, results):
    second = dynamic.run_scenes(*inputs)
    assert audit.first_difference(results, second) is None


def test_new_dynamic_dependency_forgeries_real_cli(tmp_path):
    snapshot = audit.load_bundle(BUNDLE)
    args = ["--bundle", BUNDLE]
    cases = ("nonempty_commit", "action_consequence", "corrected_memory", "contract_freeze")
    for case in cases:
        payload = copy.deepcopy(snapshot.payload)
        d = payload["dynamic_development"]
        if case == "nonempty_commit":
            d["scenes"][0]["max_direct_p5_committed"] += 1
        elif case == "action_consequence":
            d["execution"] = {"status": "PASSED", "executed": True}
        elif case == "corrected_memory":
            d["production_boundary_probes"]["correct"]["new_committed"] = True
        else:
            payload["comparison_contract"]["scientific_fairness_established"] = True
        dest = tmp_path / case
        audit.save(dest, payload, snapshot.rows, {})
        (dest / "attribution.json").write_text(json.dumps(load_analyzer(ROOT).analyze(dest, ROOT)))
        args += ["--bundle", dest]
    result = cli(*args, "--verify")
    evidence = Path(os.environ.get("S2_DYNAMIC_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "dynamic_forgery_cli.log").write_text(result.stdout + result.stderr)
    output = json.loads(result.stdout.splitlines()[-1])
    (evidence / "matrix.json").write_text(
        json.dumps({"cases": cases, "exit_code": result.returncode, "result": output}, indent=2)
    )
    assert result.returncode == 1
    assert output["results"][0]["status"] == "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    for record in output["results"][1:]:
        assert record["status"] == "REJECTED"
        assert "fresh diagnostic differs at audit." in record["error"]


def test_fresh_identifier_out_of_order_is_not_just_duplicate_rejection(inputs, tmp_path):
    """Separate chronology from duplicate IDs; public production calls only."""
    template = inputs[0]
    episode = dynamic.fixture(template, dynamic.PLANS[0])
    late = dynamic.fixture(template, dict(dynamic.PLANS[0], id="first-arrival-old-time"))
    seen = {step.after.metadata.record_id for step in episode.steps}
    assert late.steps[0].after.metadata.record_id not in seen
    assert late.steps[0].timestamp < episode.steps[-1].timestamp
    system = dynamic.StructureTwoProductionSystem(
        owner_key=episode.owner_actor_key,
        object_instance_id=episode.steps[0].object_instance_id,
        locations=episode.known_location_ids,
        authorization_scope_id=content_uuid(dynamic.ID, "first-arrival-old-time-scope"),
        action_readout=dynamic.selected_v0_6_action_readout(),
    )
    for index, step in enumerate(episode.steps):
        system.process_transition(audit.base._transition(episode, step, index))
    before = dynamic.state_readout(system)
    assert before["committed"] > 0
    with pytest.raises(ValueError, match="strictly chronological") as error:
        system.process_transition(audit.base._transition(late, late.steps[0], 0))
    after = dynamic.state_readout(system)
    assert before == after
    evidence = Path(os.environ.get("S2_DYNAMIC_EVIDENCE_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "fresh_identifier_late_input.json").write_text(
        json.dumps(
            {
                "scope": "supplemental real production test; not a CLI replay certificate",
                "source_bindings": audit.source_bindings(ROOT),
                "root": str(ROOT),
                "history_last_step": episode.steps[-1].model_dump(mode="json"),
                "first_arrival_old_step": late.steps[0].model_dump(mode="json"),
                "record_previously_seen": False,
                "error": str(error.value),
                "before": before,
                "after": after,
            },
            indent=2,
        )
    )
