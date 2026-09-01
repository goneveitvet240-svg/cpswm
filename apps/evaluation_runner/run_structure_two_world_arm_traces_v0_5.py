#!/usr/bin/env python3
"""Produce unsigned ten-arm traces after verified v0.5 Gate A."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (  # noqa: E402
    EXPECTED_ARMS,
    produce_arm_prediction_rows,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (  # noqa: E402
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (  # noqa: E402
    compute_v0_5_source_bundle,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_5 import (  # noqa: E402
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    load_frozen_validation_gate_design_v0_5,
    verify_validation_gate_report_v0_5,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402

OUTPUT_DIR = ROOT / "benchmarks/structure_two/gate_b_arm_traces_v0_5_unsigned"


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    gate_a = verify_validation_gate_report_v0_5(
        ROOT / DEFAULT_OUTPUT, repository_root=ROOT, recompute=True
    )
    if gate_a.get("gate_a_passed") is not True:
        raise ValueError("v0.5 Gate A did not authorize trace production")
    design = load_frozen_validation_gate_design_v0_5(ROOT / DEFAULT_MANIFEST, repository_root=ROOT)
    source = compute_v0_5_source_bundle(ROOT)
    manifest_path = ROOT / DEFAULT_MANIFEST
    manifest_sha256 = __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    generated = []
    contract = []
    for seed in design.validation_world_seeds:
        world = generator.sample_world(seed)
        for trajectory_seed in design.trajectory_seeds:
            for observation_seed in design.observation_seeds:
                rollout = generator.generate_rollout(
                    world,
                    trajectory_seed=trajectory_seed,
                    observation_seed=observation_seed,
                )
                generated.append((world, rollout))
                contract.append((rollout.rollout_id, len(rollout.steps)))
    expected = [
        (str(item["rollout_id"]), int(item["scored_step_count"]))
        for item in gate_a["ordered_scored_rollouts"]
    ]
    if contract != expected:
        raise ValueError("v0.5 regenerated rollout contract differs from Gate A")
    rows = produce_arm_prediction_rows(generated)
    producer_run_id = content_sha256(
        {
            "protocol": "structure-two-world-arm-trace-producer-run@0.5",
            "gate_a": gate_a["content_sha256"],
            "manifest": manifest_sha256,
            "source": source.content_sha256,
            "rollouts": [item[0] for item in contract],
        }
    )
    for arm in EXPECTED_ARMS:
        _write(
            OUTPUT_DIR / f"arm_{arm}.unsigned.json",
            {
                "arm": arm,
                "gate_a_content_sha256": gate_a["content_sha256"],
                "manifest_sha256": manifest_sha256,
                "producer_run_id": producer_run_id,
                "producer_source_bundle_sha256": source.content_sha256,
                "episode_predictions": [
                    [rollout_id, list(predictions)] for rollout_id, predictions in rows[arm]
                ],
            },
        )
    print(f"output_dir={OUTPUT_DIR}")
    print(f"producer_run_id={producer_run_id}")
    print(f"arm_count={len(EXPECTED_ARMS)}")


if __name__ == "__main__":
    main()
