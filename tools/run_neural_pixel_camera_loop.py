"""Controlled native prior + real neural checkpoint + pixel feedback in live Unity.

The hypothetical native-to-view observation likelihoods are explicit, uncalibrated
development fixtures. SSDLite receives actual pixels; semantic roles, hand contact,
instance identity, physical manipulation and full task success remain unverified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from test_continuous_state_recovery import DurableFixtureProducer  # noqa: E402
from test_native_joint_production import JointFixture  # noqa: E402
from test_structure_two_adaptive_runtime import (  # noqa: E402
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for  # noqa: E402

from cpswm.contracts.grounded_search import ObservationActionCandidate  # noqa: E402
from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder  # noqa: E402
from cpswm.system.continuous_camera_collection import collect_posterior_step  # noqa: E402
from cpswm.system.continuous_state_store import ContinuousStateStore  # noqa: E402
from cpswm.system.evaluation_operations.structure_two_selected_method import (  # noqa: E402
    TypedParticleState,
)
from cpswm.system.joint_camera_policy import (  # noqa: E402
    CameraAlternative,
    CameraModelSources,
    JointCameraProblem,
)
from cpswm.system.native_neural_production import NeuralNativeProducer  # noqa: E402
from cpswm.system.reproducibility import content_sha256, content_uuid  # noqa: E402
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext  # noqa: E402
from cpswm.system.structure_two_continuous_input import (  # noqa: E402
    ContinuousEvidenceInput,
    GroundedTransition,
    ObservationCommand,
    ObservationDelivery,
)
from cpswm.system.structure_two_particle_workspace import native_content_sha256  # noqa: E402
from cpswm.system.unity_observation import UnityObservationExecutor  # noqa: E402

ASSUMPTIONS = {
    "scope": "CONTROLLED_NATIVE_PRIOR_UNCALIBRATED_CATEGORY_VIEW_MODEL",
    "known_instance_hypothesis_view": 315.0,
    "unknown_instance_hypothesis_view": 225.0,
    "initial_heading": 270.0,
    "same_view_static_measurement_repeated": True,
    "candidate_probability_at_hypothesis_view": 0.9,
    "candidate_probability_elsewhere": 0.05,
    "aggregate_unresolved_candidate_probability": 0.5,
    "terminal_utility": "whole-atom classification 0/1 development fixture",
    "time_cost": 0.01,
    "detector_minimum_score": 0.5,
    "empirical_calibration": False,
    "formal_metric_or_architecture_selection": False,
}
SOURCES = CameraModelSources(
    observation_model_id="assumed-category-view-development@1",
    observation_artifact_sha256=content_sha256(ASSUMPTIONS),
    calibration_domain="ASSUMED_NOT_CALIBRATED",
    calibration_data_sha256=content_sha256("NO_EMPIRICAL_CALIBRATION_DATA"),
    utility_definition_id="whole-joint-atom-classification-development",
    utility_artifact_sha256=content_sha256(("0/1", 0.01)),
)


def diagnostic_house(original: dict, site: str) -> dict:
    house = json.loads(json.dumps(original))
    children = house["objects"][0]["children"]
    apple = next(x for x in children if x["id"] == "Apple|surface|2|0")
    apple["kinematic"] = True
    if site == "south":
        apple["position"]["z"] = 2 * 2.745277252197266 - apple["position"]["z"]
    elif site != "north":
        raise ValueError("explicit north or south diagnostic site required")
    pose = {
        "position": {"x": 1.25, "y": 0.95, "z": 2.745277252197266},
        "rotation": {"x": 0, "y": 270, "z": 0},
        "horizon": 30,
        "standing": True,
    }
    house["metadata"]["agent"] = pose
    house["metadata"]["agentPoses"]["default"] = pose
    house["metadata"]["cpswm_diagnostic_target"] = apple["id"]
    return house


class DiagnosticViewModel:
    sources = SOURCES

    def __init__(self, decoder):
        self.decoder = decoder

    def history(self, execution_history):
        heading = ASSUMPTIONS["initial_heading"]
        outcomes = {}
        # Arrival order, independent of runtime map insertion order.
        delivered = [(c, d) for c, d in execution_history if type(d) is ObservationDelivery]
        for command, delivery in sorted(
            delivered, key=lambda x: (x[1].received_at, str(x[0].action_id))
        ):
            if not delivery.success:
                continue
            if command.action == "RotateLeft":
                heading = (heading - command.degrees) % 360
            if command.action == "RotateRight":
                heading = (heading + command.degrees) % 360
            outcomes[heading] = self.decoder.decode(
                delivery.observations, cutoff=delivery.received_at
            )
        return heading, outcomes

    def problem(self, view, visible_prefix, *, decision_time, execution_history=()):
        heading, outcomes = self.history(execution_history)
        atoms = tuple(view.verification_belief().posterior)
        atom_headings = {
            a.particle_id: ASSUMPTIONS["unknown_instance_hypothesis_view"]
            if TypedParticleState.model_validate_json(a.state_json).instance_association_key
            == "unknown_instance"
            else ASSUMPTIONS["known_instance_hypothesis_view"]
            for a in view.atoms
        }
        found = "category_candidate" in outcomes.values()
        options = []
        for target in (225.0, 315.0):
            delta = (target - heading + 180) % 360 - 180
            if abs(delta) > 90:
                raise ValueError("diagnostic view requires unsupported rotation")
            action = "Pass" if delta == 0 else "RotateRight" if delta > 0 else "RotateLeft"
            if found or target in outcomes:
                likelihood = dict.fromkeys(
                    atoms, 1.0 if outcomes.get(target) == "category_candidate" else 0.0
                )
            else:
                likelihood = {
                    a: ASSUMPTIONS["aggregate_unresolved_candidate_probability"]
                    if a == view.unresolved_id
                    else ASSUMPTIONS["candidate_probability_at_hypothesis_view"]
                    if atom_headings[a] == target
                    else ASSUMPTIONS["candidate_probability_elsewhere"]
                    for a in atoms
                }
            candidate = ObservationActionCandidate(
                # Stable public view ID, never seeded by hidden scene hashes or RGB IDs.
                action_id=content_uuid("category-view-development", target),
                action_type="move_viewpoint" if delta else "micro_verify",
                label=f"development category view at public heading {target}",
                observation_likelihood_model_id=SOURCES.observation_model_id,
                calibration_domain=SOURCES.calibration_domain,
                outcome_likelihoods={
                    "category_candidate": likelihood,
                    "no_category_candidate": {k: 1 - v for k, v in likelihood.items()},
                },
                motion_cost=0.0,
                time_cost=ASSUMPTIONS["time_cost"],
                interruption_cost=0.0,
                privacy_cost=0.0,
                safety_cost=0.0,
            )
            options.append(
                CameraAlternative(candidate=candidate, action=action, degrees=abs(delta))
            )
        return JointCameraProblem(
            model_sources=self.sources,
            source_belief_sha256=view.content_sha256,
            source_observation_ids=tuple(
                x.envelope().identity.observation_id for x in visible_prefix
            ),
            alternatives=tuple(options),
            consolidation_decision_utilities={
                content_uuid("camera-dev", "no-consolidation"): dict.fromkeys(atoms, 0.0)
            },
            terminal_decision_utilities={a: {b: float(a == b) for b in atoms} for a in atoms},
            privacy_budget=1.0,
            minimum_net_value=0.0,
        )


def source_identity():
    files = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }
    return content_sha256(files), files


def run(output, sdk_python, binary, weights, checkpoint, site, max_actions=3):
    if type(max_actions) is not int or not 1 <= max_actions <= 20:
        raise ValueError("camera diagnostic requires an explicit 1..20 action budget")
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    source, files = source_identity()
    original = (
        ROOT / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json"
    )
    house = output / "evaluator_house.json"
    house.write_text(
        json.dumps(diagnostic_house(json.loads(original.read_text()), site), indent=2) + "\n"
    )
    pin = hashlib.sha256((checkpoint / "manifest.json").read_bytes()).hexdigest()
    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    meta = transition.after.metadata
    scope = dict(household_id=meta.household_id, session_id=meta.session_id, trace_id=meta.trace_id)
    decoder = PixelCategoryOutcomeDecoder(
        weights_path=weights, category="apple", sources=SOURCES, **scope
    )
    joint = NeuralNativeProducer(JointFixture(), checkpoint, manifest_sha256=pin)
    dependencies = {
        "decoder_binding": decoder.binding_sha256,
        "joint_binding": joint.binding_sha256,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "sdk_python_path": str(sdk_python.resolve()),
        "sdk_python_sha256": hashlib.sha256(sdk_python.resolve().read_bytes()).hexdigest(),
        "source_house_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "model_sources": SOURCES.model_dump(mode="json"),
    }
    dependency = content_sha256(dependencies)
    path = output / "state.sqlite"

    def open_store():
        return ContinuousStateStore(path, source_identity=source, dependency_identity=dependency)

    store = open_store()
    backend = DurableFixtureProducer()
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        producer=backend,
        context_builder=builder,
        state_store=store,
        joint_producer=joint,
        observation_decoder=decoder,
        **scope,
    )
    ids = stream.admit((raw_for(transition),), received_at=ciav.opportunity_time)
    backend.output = GroundedTransition(
        transition, ids, "CONTROLLED_TEST_FIXTURE", "ASSUMED_NOT_CALIBRATED"
    )
    stream.advance(cutoff=ciav.opportunity_time)
    backend.output = None
    executor = None
    rows = []
    try:
        executor = UnityObservationExecutor(
            python=sdk_python,
            worker=ROOT / "tools/unity_camera_feedback_worker.py",
            binary=binary,
            house=house,
            log_dir=output / "unity-logs",
            **scope,
        )
        initial = executor.execute(
            ObservationCommand(
                uuid4(),
                system.core.current_snapshot.snapshot_id,
                "Pass",
                0,
                "initial acquisition",
                (),
                datetime.now(UTC),
            )
        )
        stream.admit(initial.observations, received_at=initial.received_at)
        stream.advance(cutoff=initial.received_at)
        stream.produce_joint_posterior()
        native_before = native_content_sha256(system.core._particle_workspace.state_payload())
        ledger_before = system.core._hybrid_loop.ledger.export_state()
        model = DiagnosticViewModel(decoder)
        resumed = False
        for index in range(max_actions):
            before = stream.current_joint_decision_view()
            result = collect_posterior_step(
                stream, model=model, executor=executor, decision_time=datetime.now(UTC)
            )
            if result.command is None:
                rows.append(
                    {"index": index, "stopped": True, "plan": result.plan.model_dump(mode="json")}
                )
                break
            after = stream.current_joint_decision_view()
            update = stream.joint_observation_updates()[-1]
            frames = decoder.measurements(
                result.delivery.observations, cutoff=result.delivery.received_at
            )
            rows.append(
                {
                    "index": index,
                    "action_id": str(result.command.action_id),
                    "action": result.command.action,
                    "degrees": result.command.degrees,
                    "success": result.delivery.success,
                    "outcome": update.outcome,
                    "prior": {str(k): v for k, v in before.verification_belief().posterior.items()},
                    "posterior": {
                        str(k): v for k, v in after.verification_belief().posterior.items()
                    },
                    "probabilities_changed": before.verification_belief().posterior
                    != after.verification_belief().posterior,
                    "update": json.loads(json.dumps(asdict(update), default=str)),
                    "pixel_measurements": json.loads(
                        json.dumps([asdict(f) for f in frames], default=str)
                    ),
                }
            )
            if index == 0:
                expected = stream.current_joint_decision_view()
                store.close()
                store = open_store()
                decoder = PixelCategoryOutcomeDecoder(
                    weights_path=weights, category="apple", sources=SOURCES, **scope
                )
                joint = NeuralNativeProducer(JointFixture(), checkpoint, manifest_sha256=pin)
                stream = ContinuousEvidenceInput.resume(
                    store,
                    producer=DurableFixtureProducer(),
                    context_builder=builder,
                    joint_producer=joint,
                    observation_decoder=decoder,
                )
                model = DiagnosticViewModel(decoder)
                assert stream.current_joint_decision_view() == expected
                resumed = True
        final = stream.current_joint_decision_view()
        report = {
            "track": "CONTROLLED_NATIVE_PRIOR_REAL_NEURAL_PIXEL_ACTION_FEEDBACK",
            "source_sha256": source,
            "source_files": files,
            "dependencies": dependencies,
            "assumptions": ASSUMPTIONS,
            "checkpoint_manifest_sha256": pin,
            "site_evaluator_only": site,
            "actions": rows,
            "joint_producer_calls": joint.calls,
            "executed_camera_updates": len(stream.joint_observation_updates()),
            "conditional_evidence_count": len(final.observation_evidence),
            "same_view_after_resume": resumed,
            "native_batch_unchanged_by_camera": native_content_sha256(
                stream._system.core._particle_workspace.state_payload()
            )
            == native_before,
            "ledger_unchanged_by_camera": stream._system.core._hybrid_loop.ledger.export_state()
            == ledger_before,
            "natural_semantic_transitions": 0,
            "physical_manipulations": 0,
            "complete_natural_closed_loop": False,
            "source_unchanged": source_identity()[0] == source,
        }
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        assert (
            report["source_unchanged"]
            and report["native_batch_unchanged_by_camera"]
            and report["ledger_unchanged_by_camera"]
        )
        return report
    finally:
        if executor is not None:
            executor.close()
        store.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "sdk-python", "binary", "weights", "checkpoint"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--site", choices=("north", "south"), required=True)
    p.add_argument("--max-actions", type=int, default=3)
    a = p.parse_args()
    result = run(a.output, a.sdk_python, a.binary, a.weights, a.checkpoint, a.site, a.max_actions)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "executed_camera_updates",
                    "same_view_after_resume",
                    "native_batch_unchanged_by_camera",
                    "ledger_unchanged_by_camera",
                    "source_unchanged",
                )
            },
            indent=2,
        )
    )
