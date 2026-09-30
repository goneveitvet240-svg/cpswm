"""Original archive RGB-D -> controlled native likelihood, replay and recovery.

Only the semantic fixture and association are synthetic. Historical offline
commands never become commands issued by this runtime. Both position references
and both estimators remain separate development cases, not a model selection.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import numpy as np
from diagnose_offline_frontend import digest, inventory, require, source_identity
from instance_affinity_dataset import public_frame
from run_correction_replay_comparison import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    OracleProducer,
    apply_feedback,
    build_execution_feedback_bundle,
    raw_for,
)
from soft_position_dataset import public_readout
from structure_two_backbone_wiring_probe import CIAVOutcomeKind
from verify_offline_factor_capture import _json, _public

from cpswm.data_preflight import instance_affinity, soft_surface_position
from cpswm.perception_mapping import position_observation_model as position
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.controlled_position_producer import ControlledPositionProducer, packet_binding
from cpswm.system.evaluation_operations.structure_two_action_death_test import VisibleActionCase
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import canonical_json, content_sha256
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition
from cpswm.system.structure_two_particle_workspace import native_content_sha256

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "archive-controlled-native-position-bridge@1"


def write_json(path, value):
    path.write_text(canonical_json(value) + "\n")


def first_seed(record, full, model, pin):
    """Compare the complete public frame before selecting by public order only."""
    fresh = public_readout(record, model, pin)
    require(content_sha256(full) == content_sha256(fresh), "parent public readout differs")
    for candidate in sorted(fresh["candidates"], key=lambda c: (c["method"], c["id"])):
        grid = candidate["grid_pixels_uv"]
        neighborhoods = [n for n in fresh["neighborhoods"] if n["pixels_uv"] == grid]
        if not grid:
            continue
        require(len(neighborhoods) == 1, "nonunique complete public neighborhood")
        neighborhood = neighborhoods[0]
        for uv, valid in zip(grid, neighborhood["valid"], strict=True):
            if not valid:
                continue
            seeds = [
                s
                for s in fresh["seeds"]
                if s["neighborhood_id"] == neighborhood["neighborhood_id"] and s["pixel_uv"] == uv
            ]
            require(len(seeds) == 1 and seeds[0]["valid"] is True, "public seed differs")
            return {k: candidate[k] for k in ("method", "id", "box")}, uv, seeds[0], neighborhood
    return None


def correspondence(record, full, model, pin, chosen):
    """Bind complete single-box support to the original multi-box neighborhood.

    Input/seed IDs legitimately differ because the provenance and candidate set
    differ. Neither ID is rewritten, and equal XYZ alone is never sufficient.
    """
    candidate, uv, seed, neighborhood = chosen
    packet = packet_binding(record["delivery"].observations)
    single = soft_surface_position.readout_frame(
        record["rgb"],
        record["depth"],
        record["camera"],
        [candidate],
        model,
        pin,
        provenance=dict(
            source_sha256=packet["raw_sha256"],
            receipt_sha256=record["public_metadata"]["receipt_sha256"],
            observation_ids=packet["observation_ids"],
            payload_sha256=record["public_metadata"]["payload_sha256"],
        ),
    )
    require(len(single["neighborhoods"]) == 1, "single candidate support missing")
    small = single["neighborhoods"][0]
    for key in ("pixels_uv", "rgb_values", "rendered_depth_m", "valid", "world_points_m"):
        require(small[key] == neighborhood[key], "full neighborhood correspondence differs: " + key)
    require(
        candidate in neighborhood["sources"] and small["sources"] == [candidate],
        "source membership differs",
    )
    single_seed = next(s for s in single["seeds"] if s["pixel_uv"] == uv)
    require(single_seed["coefficients"] == seed["coefficients"], "complete seed weights differ")
    observations = {}
    for estimator in position.ESTIMATORS:
        a = next(
            o
            for o in full["observations"]
            if o["seed_id"] == seed["seed_id"] and o["estimator"] == estimator
        )
        b = next(
            o
            for o in single["observations"]
            if o["seed_id"] == single_seed["seed_id"] and o["estimator"] == estimator
        )
        for key in (
            "estimator",
            "estimator_pin",
            "domain_id",
            "frame_id",
            "action_id",
            "valid_at",
            "world_point_m",
            "available",
            "reason",
        ):
            require(a[key] == b[key], "complete observation correspondence differs: " + key)
        observations[estimator] = b
    receipt = dict(
        packet=packet,
        candidate=candidate,
        seed_uv=uv,
        full_input_sha256=full["input_sha256"],
        single_input_sha256=single["input_sha256"],
        full_neighborhood_id=neighborhood["neighborhood_id"],
        single_neighborhood_id=small["neighborhood_id"],
        full_seed_id=seed["seed_id"],
        single_seed_id=single_seed["seed_id"],
        full_sources=neighborhood["sources"],
        single_sources=small["sources"],
        neighborhood=small,
        coefficients=single_seed["coefficients"],
        observations=observations,
        original_ids_preserved=True,
        full_support_compared=True,
    )
    return receipt


def select_input(args, bundle):
    """Load only public frames/candidates for selection; parent verification is separate."""
    binding = bundle.report["parent_binding"]
    require(
        digest(args.collection / "inventory.json")
        == binding["collection_inventory_sha256"]
        == args.inventory_sha256,
        "collection external pin differs",
    )
    original_inventory = _json(args.collection / "inventory.json")
    affinity_files = binding["affinity"]["output_files"]
    model_path = args.affinity_results / "experiment/model.json"
    require(
        digest(model_path) == affinity_files["model.json"], "parent affinity model bytes differ"
    )
    model = _json(model_path)
    pin = instance_affinity.checkpoint_sha256(model)
    require(pin == soft_surface_position.FIXED_AFFINITY_PIN, "fixed original affinity differs")
    instance_affinity.restore(model, pin)
    frontends = {}
    for method in ("fasterrcnn", "ssdlite"):
        path = args.frontends / method / "public.json"
        require(
            digest(path) == binding["frontends"]["files"][method]["public.json"],
            "frontend public bytes differ",
        )
        frontends[method] = _json(path)
        require(len(frontends[method]) == 96, "incomplete public frontends")
    skipped = []
    for house in range(1, 13):
        folder = args.collection / f"house-{house:02d}"
        for path in [
            folder / "capture.json",
            *(folder / "public" / f"{n:03d}-state.json" for n in range(8)),
        ]:
            require(
                digest(path) == original_inventory[path.relative_to(args.collection).as_posix()],
                "original public bytes differ",
            )
        raw, _ = _public(folder / "public", _json(folder / "capture.json")["provenance"])
        for local, (command, delivery, _) in enumerate(raw):
            ordinal = (house - 1) * 8 + local
            record = public_frame(command, delivery, {m: frontends[m][ordinal] for m in frontends})
            full = bundle.load_json(f"frames/{ordinal:03d}/public.json")
            chosen = first_seed(record, full, model, pin)
            if chosen is None:
                skipped.append(dict(ordinal=ordinal, reason="no_public_valid_seed"))
                continue
            receipt = correspondence(record, full, model, pin, chosen)
            receipt.update(
                frame_ordinal=ordinal,
                public_state_sha256=original_inventory[
                    f"house-{house:02d}/public/{local:03d}-state.json"
                ],
                skipped_frames=skipped,
            )
            return record, model, pin, receipt
    raise ValueError("no public valid seed in all 96 frames; no substitute selected")


def verify_ancestors(args, bundle):
    """Recheck retained upstream originals, not only the 302 position outputs."""
    binding = bundle.report["parent_binding"]
    collection = inventory(args.collection)
    require(
        collection["inventory.json"]
        == args.inventory_sha256
        == binding["collection_inventory_sha256"],
        "ancestor collection pin differs",
    )
    require(
        {k: v for k, v in collection.items() if k != "inventory.json"}
        == _json(args.collection / "inventory.json"),
        "ancestor collection members changed",
    )
    capture = _json(args.collection / "configuration.json")
    require(
        source_identity(args.capture_source) == capture["source_files"],
        "ancestor capture source changed",
    )
    for key in ("controls", "affinity"):
        directory, source = getattr(args, key + "_results"), getattr(args, key + "_source")
        original = binding[key]
        require(
            digest(directory / "case-results.json")
            == original["ledger_sha256"]
            == getattr(args, key + "_ledger_sha256"),
            "ancestor ledger changed: " + key,
        )
        require(
            inventory(directory / "experiment") == original["output_files"],
            "ancestor output members changed: " + key,
        )
        require(
            source_identity(source) == original["source_files"], "ancestor source changed: " + key
        )
    original = binding["frontends"]
    require(
        digest(args.frontends / "case-results.json")
        == original["ledger_sha256"]
        == args.frontend_ledger_sha256,
        "ancestor frontend ledger changed",
    )
    require(
        source_identity(args.frontend_source) == original["source_files"],
        "ancestor frontend source changed",
    )
    for method in ("fasterrcnn", "ssdlite"):
        require(
            inventory(args.frontends / method) == original["files"][method],
            "ancestor frontend members changed",
        )


def adapted_probe(delivery, *, case_document=None):
    """Shift every synthetic record; never modify the original archive packet."""
    original = BackboneWiringProbe.build(seed=171)
    if case_document is not None:
        return BackboneWiringProbe(
            case=VisibleActionCase.model_validate(case_document), system=original.system
        )
    envs = [r.envelope() for r in delivery.observations]
    scope = envs[0].identity
    anchor = max(
        [delivery.received_at] + [e.capture_time for e in envs] + [e.arrival_time for e in envs]
    ) + timedelta(seconds=1)
    delta = anchor - original.observed_days()[0].before.detection_time
    days = []
    for day in original.case.days:
        data = day.model_dump(mode="python")
        for name in ("before", "after", "actor_evidence", "mechanism_evidence", "role_evidence"):
            old = getattr(day, name)
            if old is None:
                continue
            value = old.model_dump(mode="python")
            meta = value["metadata"]
            for key in ("household_id", "session_id", "trace_id"):
                meta[key] = getattr(scope, key)
            meta["recorded_time"] += delta
            for key in ("detection_time", "evidence_time"):
                if value.get(key) is not None:
                    value[key] += delta
            data[name] = type(old).model_validate(value)
        days.append(type(day).model_validate(data))
    case = VisibleActionCase.model_validate(
        {**original.case.model_dump(mode="python"), "days": days}
    )
    return BackboneWiringProbe(case=case, system=original.system)


def context_builder(probe):
    def builder(system, item, when, step):
        probe.system = system
        probe.step_index = step
        return AdaptiveExecutionContext(
            router_features=probe.router_features(),
            step_index=step,
            ciav_input=probe.ciav_input(
                item.transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )

    return builder


def make_joint(config):
    candidate = ControlledPositionProducer(
        configuration=config["configuration"], **config["models"]
    )
    joint = NeuralNativeProducer(
        candidate,
        Path(config["checkpoint"]),
        manifest_sha256=config["checkpoint_manifest_sha256"],
        use_owned_visual_context=False,
    )
    return candidate, joint


def open_case(path, config, *, resume=False):
    original = {
        k: v
        for k, v in config.items()
        if k not in {"source_identity", "expected_snapshot", "next_neutral_index"}
    }
    require(
        content_sha256(original) == config["source_identity"],
        "persisted bridge configuration differs",
    )
    probe = adapted_probe(None, case_document=config["visible_case"])
    backend = OracleProducer()
    candidate, joint = make_joint(config)
    store = ContinuousStateStore(
        path,
        source_identity=config["source_identity"],
        dependency_identity=content_sha256(sys.version),
    )
    builder = context_builder(probe)
    try:
        if resume:
            stream = ContinuousEvidenceInput.resume(
                store, producer=backend, context_builder=builder, joint_producer=joint
            )
        else:
            meta = probe.observed_days()[0].after.metadata
            stream = ContinuousEvidenceInput(
                system=probe.system,
                execution_lane="registered_p5_first",
                producer=backend,
                context_builder=builder,
                household_id=meta.household_id,
                session_id=meta.session_id,
                trace_id=meta.trace_id,
                state_store=store,
                joint_producer=joint,
            )
    except BaseException:
        store.close()
        raise
    return dict(
        probe=probe, backend=backend, candidate=candidate, joint=joint, store=store, stream=stream
    )


def advance(case, index):
    transition = case["probe"].transition_for(case["probe"].observed_days()[index])
    when = transition.after.detection_time + timedelta(minutes=1)
    stream = case["stream"]
    ids = stream.admit((raw_for(transition, index),), received_at=when)
    case["backend"].output = GroundedTransition(
        transition, ids, "CONTROLLED_ARCHIVE_BRIDGE_SEMANTICS", "ASSUMED_NOT_EMPIRICAL"
    )
    try:
        stream.advance(cutoff=when)
        stream.produce_joint_posterior()
    finally:
        case["backend"].output = None


def numerical_state(case):
    workspace = case["stream"]._system.core._particle_workspace
    logs, aggregate = workspace.previous_weight_evidence(workspace.batch).normalized_logs()
    result = {}
    for weight in workspace.batch.particle_weights:
        record = workspace.records[weight.particle_id]
        key = "unknown" if record.state.instance_association_key == "unknown_instance" else "known"
        require(key not in result and weight.accepted, "unexpected native support")
        s = record.statistics
        result[key] = dict(
            probability=weight.posterior_probability,
            normalized_log_weight=logs[weight.particle_id],
            information=s.information,
            information_vector=s.information_vector,
            alpha=s.alpha,
            a=s.a,
            b=s.b,
        )
    require(set(result) == {"known", "unknown"}, "native branch lost")
    result["aggregate"] = dict(
        probability=workspace.batch.unresolved_probability, normalized_log_weight=aggregate
    )
    return json.loads(canonical_json(result))


def same_numerical(a, b):
    for key in ("known", "unknown"):
        require(set(a[key]) == set(b[key]), "numerical fields differ")
        for field in a[key]:
            require(
                np.allclose(a[key][field], b[key][field], rtol=0, atol=1e-12),
                "native continuation changed " + key + "/" + field,
            )
    for field in a["aggregate"]:
        require(
            np.isclose(a["aggregate"][field], b["aggregate"][field], rtol=0, atol=1e-12),
            "aggregate changed",
        )


def snapshot(case):
    stream = case["stream"]
    core = stream._system.core
    return dict(
        workspace=native_content_sha256(core._particle_workspace.state_payload()),
        ledger=native_content_sha256(core._hybrid_loop.ledger.export_state()),
        view=native_content_sha256(stream.current_joint_decision_view()),
        producer=native_content_sha256(case["joint"].checkpoint_state()),
    )


def duplicate_check(case):
    before = snapshot(case)
    case["stream"].produce_joint_posterior()
    require(snapshot(case) == before, "duplicate publication mutated owner state")


def check_gaussian(model, diagnostic, state):
    """Independent small dense arithmetic; does not call position.condition."""
    if not diagnostic["active"]:
        for key in ("known", "unknown", "aggregate"):
            require(np.isclose(state[key]["probability"], 1 / 3), "no-factor initial prior differs")
        return
    point = np.asarray(diagnostic["public_observation"]["world_point_m"], dtype=float)
    noise = np.asarray(model["covariance"], dtype=float)
    z = point - np.asarray(model["bias"], dtype=float)
    predictive = np.eye(3) + noise
    sign, logdet = np.linalg.slogdet(predictive)
    require(sign == 1, "independent predictive covariance invalid")
    known = float(-0.5 * (3 * np.log(2 * np.pi) + logdet + z @ np.linalg.solve(predictive, z)))
    unknown = float(-0.5 * (3 * np.log(2 * np.pi * 100) + point @ point / 100))
    logs = np.asarray([known, unknown, unknown])
    logs = logs - logs.max()
    logs -= np.log(np.exp(logs).sum())
    for key, value in zip(("known", "unknown", "aggregate"), logs, strict=True):
        require(
            np.isclose(state[key]["normalized_log_weight"], value, rtol=1e-12, atol=1e-12),
            "independent Gaussian weight differs",
        )
    information = np.eye(6)
    information[:3, :3] += np.linalg.inv(noise)
    eta = np.r_[np.linalg.solve(noise, z), [0.0, 0.0, 0.0]]
    require(
        np.allclose(state["known"]["information"], information, rtol=1e-12, atol=1e-12),
        "independent precision differs",
    )
    require(
        np.allclose(state["known"]["information_vector"], eta, rtol=1e-12, atol=1e-12),
        "independent information vector differs",
    )
    require(
        np.isclose(
            diagnostic["known"]["observation_log_likelihood"], known, rtol=1e-12, atol=1e-12
        ),
        "preupdate likelihood differs",
    )


def resume_worker(config_path, external_pin, result_path):
    require(
        not config_path.is_symlink() and not result_path.exists(),
        "resume paths must retain original configuration and new output",
    )
    require(digest(config_path) == external_pin, "resume configuration external pin differs")
    config = _json(config_path)
    require(source_identity(ROOT) == config["source_files"], "resume source differs")
    case = open_case(config_path.parent / "state.db", config, resume=True)
    try:
        require(snapshot(case) == config["expected_snapshot"], "fresh SQLite state differs")
        before = numerical_state(case)
        duplicate_check(case)
        if config["next_neutral_index"] is not None:
            advance(case, config["next_neutral_index"])
            same_numerical(before, numerical_state(case))
        require(not case["stream"]._observation_commands, "archive became an issued camera command")
        write_json(
            result_path,
            dict(
                initial_snapshot=config["expected_snapshot"],
                final_snapshot=snapshot(case),
                numerical=numerical_state(case),
                consumed_keys=len(case["candidate"].consumed_keys),
                duplicate_unchanged=True,
                next_neutral_index=config["next_neutral_index"],
                physical_camera_commands=0,
            ),
        )
    finally:
        case["store"].close()


def fresh_process(folder, config, case, *, next_index, phase):
    payload = {**config, "expected_snapshot": snapshot(case), "next_neutral_index": next_index}
    cfg = folder / f"resume-{phase}.json"
    result = folder / f"resume-{phase}-result.json"
    write_json(cfg, payload)
    case["store"].close()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--resume-config",
        str(cfg),
        "--resume-config-sha256",
        digest(cfg),
        "--resume-result",
        str(result),
    ]
    env = os.environ.copy()
    env.update(
        PYTHONPATH=os.pathsep.join(str(ROOT / x) for x in ("src", "tests", "tools")),
        OPENBLAS_NUM_THREADS="1",
    )
    with (folder / f"resume-{phase}.log").open("w") as log:
        run = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    require(run.returncode == 0, "fresh SQLite subprocess failed; see retained log")
    data = _json(result)
    case = open_case(folder / "state.db", config, resume=True)
    require(snapshot(case) == data["final_snapshot"], "fresh subprocess final state differs")
    return case


def retract_selected(case, selected_id):
    core = case["stream"]._system.core
    targets = [
        (rid, e)
        for rid, e in core._committed_events.items()
        if str(e.source_record_id) == selected_id
    ]
    require(len(targets) == 1, "bound published semantic source not uniquely retractable")
    bundles = [
        build_execution_feedback_bundle(
            case["probe"],
            revision_id=rid,
            location_id=e.location_id,
            belief_snapshot_id=e.belief_snapshot_id,
            when=e.evidence.event_time,
            opportunity_id=e.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, e in targets
    ]
    outcome = apply_feedback(
        case["stream"],
        bundles,
        case["probe"].observed_days()[3].after.detection_time + timedelta(hours=2),
    )
    require(all("retract" in row["operations"] for row in outcome), "feedback did not retract")
    require(all(rid not in core._observed_events for rid, _ in targets), "withdrawn source remains")
    before = native_content_sha256(core._hybrid_loop.ledger.export_state())
    case["stream"].replay_joint_posterior()
    require(
        native_content_sha256(core._hybrid_loop.ledger.export_state()) == before,
        "native replay altered semantic ledger",
    )
    require(case["candidate"].consumed_keys == [], "withdrawn packet remained consumed")


def run_arm(
    folder,
    *,
    delivery,
    visible_case,
    configuration,
    models,
    checkpoint,
    checkpoint_pin,
    source_files,
    external_binding,
):
    folder.mkdir(parents=True)
    config = dict(
        schema=SCHEMA,
        configuration=configuration,
        models=models,
        visible_case=visible_case,
        checkpoint=str(checkpoint.resolve()),
        checkpoint_manifest_sha256=checkpoint_pin,
        source_files=source_files,
        external_binding=external_binding,
    )
    config["source_identity"] = content_sha256(config)
    write_json(folder / "configuration.json", config)
    case = open_case(folder / "state.db", config)
    try:
        original = packet_binding(delivery.observations)
        case["stream"].admit(delivery.observations, received_at=delivery.received_at)
        advance(case, 0)
        selected_id = str(
            case["stream"]
            ._system.core.current_posterior_projection_source()
            .transition.after.metadata.record_id
        )
        diagnostic = deepcopy(case["candidate"].last_diagnostic)
        write_json(folder / "active-diagnostic.json", diagnostic)
        active = numerical_state(case)
        check_gaussian(models["position_model"], diagnostic, active)
        duplicate_check(case)
        for index in (1, 2):
            advance(case, index)
            same_numerical(active, numerical_state(case))
        require(
            len(case["candidate"].consumed_keys) == int(configuration["enabled"]),
            "unexpected measurement count",
        )
        case = fresh_process(folder, config, case, next_index=3, phase="active")
        same_numerical(active, numerical_state(case))
        retract_selected(case, selected_id)
        removed = numerical_state(case)
        case = fresh_process(folder, config, case, next_index=None, phase="retracted")
        same_numerical(removed, numerical_state(case))
        require(packet_binding(delivery.observations) == original, "archive raw packet mutated")
        require(not case["stream"]._observation_commands, "physical command fabricated")
        return dict(
            active=active,
            after_retraction=removed,
            diagnostic=diagnostic,
            duplicate_unchanged=True,
            neutral_steps=3,
            fresh_processes=2,
            physical_camera_commands=0,
            raw_packet_unchanged=True,
        )
    finally:
        case["store"].close()


def run_comparison(
    output,
    *,
    record,
    receipt,
    affinity_model,
    affinity_pin,
    model_entries,
    checkpoint,
    checkpoint_pin,
    external_binding,
):
    output.mkdir(parents=True, exist_ok=False)
    before = source_identity(ROOT)
    probe = adapted_probe(record["delivery"])
    visible = probe.case.model_dump(mode="json")
    write_json(output / "visible-case.json", visible)
    write_json(output / "public-correspondence.json", receipt)
    config = dict(
        semantic_record_id=str(probe.observed_days()[0].after.metadata.record_id),
        packet=receipt["packet"],
        candidate=receipt["candidate"],
        seed_uv=receipt["seed_uv"],
        enabled=True,
    )
    results = {}
    for estimator in position.ESTIMATORS:
        for reference in position.REFERENCES:
            name = estimator + "/" + reference
            entry = model_entries[name]
            if entry["status"] == "fit_failed":
                results[name] = dict(
                    status="unavailable", reason=entry["reason"], replacement_created=False
                )
                continue
            require(entry["status"] == "fitted", "unknown parent model status")
            model = position.restore(entry["model"], entry["pin"])
            require(
                (model["estimator"], model["reference_kind"]) == (estimator, reference),
                "model identity differs",
            )
            models = dict(
                affinity_model=affinity_model,
                affinity_pin=affinity_pin,
                position_model=model,
                position_pin=entry["pin"],
            )
            arms = {}
            for enabled, arm in ((True, "active"), (False, "no_factor")):
                arms[arm] = run_arm(
                    output / name / arm,
                    delivery=record["delivery"],
                    visible_case=visible,
                    configuration={**config, "enabled": enabled},
                    models=models,
                    checkpoint=checkpoint,
                    checkpoint_pin=checkpoint_pin,
                    source_files=before,
                    external_binding=external_binding,
                )
            same_numerical(
                arms["active"]["after_retraction"], arms["no_factor"]["after_retraction"]
            )
            observed = arms["active"]["diagnostic"]["public_observation"]
            expected_observation = receipt["observations"][estimator]
            require(
                all(observed[k] == expected_observation[k] for k in observed),
                "published observation differs from full correspondence",
            )
            # Keep real diagnostic source UUIDs in per-arm files, not the reproducible comparison.
            for arm in arms.values():
                diag = arm.pop("diagnostic")
                if "known" in diag:
                    diag["known"].pop("evidence_cluster_id")
                arm["likelihood_diagnostic"] = {
                    k: diag[k] for k in ("active", "known", "unknown_log_likelihood") if k in diag
                }
            results[name] = dict(
                status="consumed", model_pin=entry["pin"], arms=arms, replay_equals_no_factor=True
            )
    require(source_identity(ROOT) == before, "bridge source changed")
    report = dict(
        schema=SCHEMA,
        source_files=before,
        external_binding=external_binding,
        public_correspondence_sha256=content_sha256(receipt),
        visible_case_sha256=content_sha256(visible),
        checkpoint_manifest_sha256=checkpoint_pin,
        results=results,
        natural_identity=False,
        natural_factor_completed=False,
        synthetic_semantic_association=True,
        independent_acceptance=False,
        formal_reference_selected=False,
        orientation_observed=False,
        camera_action_utility_tested=False,
        scope="ORIGINAL_ARCHIVE_PUBLIC_INPUT_WITH_CONTROLLED_SEMANTIC_ASSOCIATION_NATIVE_ENGINEERING_ONLY",
    )
    write_json(output / "report.json", report)
    write_json(output / "members.json", inventory(output))
    return report


def verify_saved_consequences(saved, fresh, report):
    """Self-signed member hashes alone do not authenticate persisted owner state."""
    before = inventory(saved)
    require(set(before) == set(inventory(fresh)), "saved bridge member set differs from fresh run")
    for name in ("visible-case.json", "public-correspondence.json"):
        require(
            (saved / name).read_bytes() == (fresh / name).read_bytes(),
            "saved public bridge input differs",
        )
    for name, result in report["results"].items():
        if result["status"] != "consumed":
            continue
        for arm in ("active", "no_factor"):
            directory = saved / name / arm
            expected = _json(fresh / name / arm / "configuration.json")
            require(
                content_sha256(_json(directory / "configuration.json")) == content_sha256(expected),
                "saved owner configuration differs from original inputs",
            )
            with tempfile.TemporaryDirectory(prefix="cpswm-bridge-db-copy-") as temporary:
                copy = Path(temporary) / "state.db"
                shutil.copy2(directory / "state.db", copy)
                restored = open_case(copy, expected, resume=True)
                try:
                    same_numerical(
                        numerical_state(restored), result["arms"][arm]["after_retraction"]
                    )
                    duplicate_check(restored)
                    require(
                        not restored["candidate"].consumed_keys,
                        "saved withdrawn measurement remains",
                    )
                    require(
                        not restored["stream"]._observation_commands,
                        "saved archive has camera commands",
                    )
                finally:
                    restored["store"].close()
            # The source UUID is runtime generated. Every numerical field is checked.
            actual = _json(directory / "active-diagnostic.json")
            target = _json(fresh / name / arm / "active-diagnostic.json")
            for item in (actual, target):
                for key in ("semantic_record_id", "native_after_record_id"):
                    item.pop(key)
                if "known" in item:
                    item["known"].pop("evidence_cluster_id")
            require(
                content_sha256(actual) == content_sha256(target),
                "saved active diagnostic differs from fresh computation",
            )
    require(inventory(saved) == before, "saved bridge changed during verification")


def main():
    import torch

    torch.set_num_threads(2)
    if "--resume-config" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--resume-config", type=Path, required=True)
        parser.add_argument("--resume-config-sha256", required=True)
        parser.add_argument("--resume-result", type=Path, required=True)
        args = parser.parse_args()
        resume_worker(args.resume_config, args.resume_config_sha256, args.resume_result)
        return
    from verified_position_parent import add_parent_arguments, verify_position_parent

    parser = argparse.ArgumentParser(description=__doc__)
    add_parent_arguments(parser)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    require(not args.output.is_symlink(), "symlink bridge output")
    output = args.output.resolve()
    require(args.verify or not output.exists(), "refuse to overwrite bridge output")
    for value in vars(args).values():
        if isinstance(value, Path) and value != args.output:
            p = value.resolve()
            require(
                not output.is_relative_to(p) and not p.is_relative_to(output),
                "bridge output overlaps input",
            )
    bundle = verify_position_parent(args)
    verify_ancestors(args, bundle)
    record, affinity_model, affinity_pin, receipt = select_input(args, bundle)
    entries = {}
    for name, status in bundle.report["model_status"].items():
        model = bundle.load_json("models/" + name + ".json")
        entries[name] = (
            {**status, "model": model, "pin": status["sha256"]}
            if status["status"] == "fitted"
            else status
        )

    def execute(directory):
        return run_comparison(
            directory,
            record=record,
            receipt=receipt,
            affinity_model=affinity_model,
            affinity_pin=affinity_pin,
            model_entries=entries,
            checkpoint=args.checkpoint,
            checkpoint_pin=args.checkpoint_manifest_sha256,
            external_binding=bundle.binding,
        )

    if args.verify:
        members = _json(output / "members.json")
        require(
            inventory(output) == {**members, "members.json": digest(output / "members.json")},
            "saved bridge member bytes differ",
        )
        with tempfile.TemporaryDirectory(prefix="cpswm-archive-bridge-verify-") as temporary:
            fresh = execute(Path(temporary) / "experiment")
            require(
                content_sha256(fresh) == content_sha256(_json(output / "report.json")),
                "fresh bridge consequences differ",
            )
            verify_saved_consequences(output, Path(temporary) / "experiment", fresh)
    else:
        execute(output)
    bundle.assert_unchanged()
    verify_ancestors(args, bundle)
    print(json.dumps(dict(complete=True, verify=args.verify, scope=SCHEMA)))


if __name__ == "__main__":
    main()
