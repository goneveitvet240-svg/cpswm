"""Fit and evaluate a local pose measurement model on separately supplied labels.

Input JSON has 'fit' and 'heldout' arrays of PoseLabel fields. PoseObservation
fields reference and observed, and label truth, are PoseState mappings. No
simulator metadata or predicted label is substituted for an independent label.
"""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.perception_mapping.pose_observation_model import (  # noqa: E402
    GaussianPoseObservationModel,
    PoseLabel,
    PoseObservation,
)
from cpswm.system.continuous_state_codec import StateCodec  # noqa: E402
from cpswm.system.structure_two_pose import PoseState  # noqa: E402


def parse_label(payload):
    payload = dict(payload)
    obs = dict(payload.pop("observation"))
    observation = PoseObservation(
        source_record_id=UUID(obs.pop("source_record_id")),
        reference=PoseState.model_validate(obs.pop("reference")),
        observed=PoseState.model_validate(obs.pop("observed")),
        **obs,
    )
    return PoseLabel(
        observation=observation, truth=PoseState.model_validate(payload.pop("truth")), **payload
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    if set(payload) != {"fit", "heldout"}:
        raise ValueError("separate fit and heldout pose-label arrays required")
    model = GaussianPoseObservationModel.fit(tuple(map(parse_label, payload["fit"])))
    report = model.evaluate(tuple(map(parse_label, payload["heldout"])))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "model.json").write_text(StateCodec().dumps(model))
    (args.output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, allow_nan=False))


if __name__ == "__main__":
    main()
