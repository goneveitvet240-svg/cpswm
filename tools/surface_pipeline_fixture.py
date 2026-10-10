"""Explicit controlled semantic bootstrap for the natural surface integration probe.

This is not a natural event/actor recognizer. Existing semantic and neural test
fixtures are retained verbatim while the camera inputs and surface pipeline run.
"""

from datetime import timedelta
from pathlib import Path

from run_correction_replay_comparison import build
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_native_position_production import advance, fixture_models
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.mask_surface_support import MaskSurfaceSupportProducer
from cpswm.system.native_neural_production import NeuralNativeProducer
from cpswm.system.reproducibility import content_sha256

SOURCE = content_sha256("six-step-natural-surface-controlled-semantic-bootstrap@1")


def make_case(
    path,
    checkpoints,
    weights,
    mask_weights,
    *,
    schedule,
    enabled=True,
    policy=None,
    object_frontend=None,
):
    selected_index = 1
    selected = BackboneWiringProbe.build(seed=171).observed_days()[selected_index].after
    config = dict(
        semantic_record_id=str(selected.metadata.record_id),
        enabled=enabled,
        weights_path=str(Path(weights).resolve()),
        mask_weights_path=str(Path(mask_weights).resolve()),
        shared_fraction=0.5,
        unknown_prior=0.2,
        pipeline=policy or dict(mode="fixed_scan", schedule=schedule, budget=len(schedule)),
    )
    if object_frontend is not None:
        config["object_frontend"] = object_frontend
    models = fixture_models()
    candidate = MaskSurfaceSupportProducer(configuration=config, **models)
    checkpoint, pin = checkpoints[ARMS[1]]
    joint = NeuralNativeProducer(candidate, checkpoint, manifest_sha256=pin)
    probe, backend, stream, store, builder = build(
        path,
        seed=171,
        source=SOURCE,
        joint_producer=joint,
        observation_decoder=RGBDSupportDecoder(),
    )
    case = dict(
        probe=probe,
        backend=backend,
        stream=stream,
        store=store,
        builder=builder,
        candidate=candidate,
        joint=joint,
        models=models,
        config=config,
        rows=(),
        checkpoint=checkpoint,
        pin=pin,
        selected_index=selected_index,
    )
    for index in range(selected_index):
        advance(case, index)
    case["when"] = advance(case, selected_index) + timedelta(seconds=1)
    return case


def restore_joint(config):
    candidate = MaskSurfaceSupportProducer(configuration=config["config"], **config["models"])
    return NeuralNativeProducer(
        candidate, Path(config["checkpoint"]), manifest_sha256=config["pin"]
    )
