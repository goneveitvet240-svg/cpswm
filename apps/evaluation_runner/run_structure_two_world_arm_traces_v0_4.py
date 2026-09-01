#!/usr/bin/env python3
"""Produce the exact unsigned ten-arm traces authorized by v0.4 Gate A."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (  # noqa: E402
    EXPECTED_ARMS,
    compute_producer_source_bundle,
    produce_arm_prediction_rows,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (  # noqa: E402
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (  # noqa: E402
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    load_frozen_validation_gate_design,
    verify_validation_gate_report,
)
from cpswm.system.reproducibility import content_sha256  # noqa: E402

DEFAULT_UNSIGNED_DIR = Path("benchmarks/structure_two/gate_b_arm_traces_v0_4_unsigned")


def _write_new_json(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing producer artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_UNSIGNED_DIR)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("unsigned trace directory is non-empty; refusing to mix runs")

    gate_a = verify_validation_gate_report(
        ROOT / DEFAULT_OUTPUT,
        repository_root=ROOT,
        recompute=True,
    )
    if gate_a.get("gate_a_passed") is not True or gate_a.get("gate_b_allowed") is not True:
        raise ValueError("verified fresh-world Gate A did not authorize trace production")
    design = load_frozen_validation_gate_design(
        ROOT / DEFAULT_MANIFEST,
        repository_root=ROOT,
    )
    manifest = json.loads((ROOT / DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    contract = manifest["gate_b_contract"]
    if tuple(contract["expected_arms"]) != EXPECTED_ARMS:
        raise ValueError("manifest arm order differs from the official v0.4 adapter")

    source_bundle = compute_producer_source_bundle(ROOT)
    if source_bundle.content_sha256 != contract["producer_source_bundle_sha256"]:
        raise ValueError("current producer source differs from the preregistered bundle")

    generator = StructureTwoWorldGeneratorV02(design.distribution)
    generated: list[tuple[object, object]] = []
    observed_contract: list[tuple[str, int]] = []
    for world_seed in design.validation_world_seeds:
        world = generator.sample_world(world_seed)
        for trajectory_seed in design.trajectory_seeds:
            for observation_seed in design.observation_seeds:
                rollout = generator.generate_rollout(
                    world,
                    trajectory_seed=trajectory_seed,
                    observation_seed=observation_seed,
                )
                generated.append((world, rollout))
                observed_contract.append((rollout.rollout_id, len(rollout.steps)))
    expected_contract = [
        (str(item["rollout_id"]), int(item["scored_step_count"]))
        for item in gate_a["ordered_scored_rollouts"]
    ]
    if observed_contract != expected_contract:
        raise ValueError("regenerated rollout order or length differs from Gate A")

    rows = produce_arm_prediction_rows(generated)  # type: ignore[arg-type]
    manifest_sha256 = str(gate_a["provenance"]["manifest_sha256"])
    producer_run_id = content_sha256(
        {
            "protocol": "structure-two-world-arm-trace-producer-run@0.4",
            "gate_a_content_sha256": gate_a["content_sha256"],
            "manifest_sha256": manifest_sha256,
            "producer_source_bundle_sha256": source_bundle.content_sha256,
            "ordered_rollout_ids": [item[0] for item in observed_contract],
        }
    )
    for arm in EXPECTED_ARMS:
        payload = {
            "arm": arm,
            "gate_a_content_sha256": gate_a["content_sha256"],
            "manifest_sha256": manifest_sha256,
            "producer_run_id": producer_run_id,
            "producer_source_bundle_sha256": source_bundle.content_sha256,
            "episode_predictions": [
                [rollout_id, list(predictions)] for rollout_id, predictions in rows[arm]
            ],
        }
        _write_new_json(output_dir / f"arm_{arm}.unsigned.json", payload)
    receipt = {
        "protocol": "structure-two-world-arm-trace-producer-receipt@0.4",
        "producer_run_id": producer_run_id,
        "producer_source_bundle_sha256": source_bundle.content_sha256,
        "producer_source_files": [list(item) for item in source_bundle.files],
        "gate_a_content_sha256": gate_a["content_sha256"],
        "manifest_sha256": manifest_sha256,
        "arm_count": len(EXPECTED_ARMS),
        "rollout_count": len(observed_contract),
        "ordered_rollout_contract_sha256": content_sha256(observed_contract),
    }
    receipt["content_sha256"] = content_sha256(receipt)
    _write_new_json(output_dir / "producer_receipt.json", receipt)
    print(f"output_dir={output_dir}")
    print(f"producer_run_id={producer_run_id}")
    print(f"producer_source_bundle_sha256={source_bundle.content_sha256}")
    print(f"arm_count={len(EXPECTED_ARMS)}")
    print(f"rollout_count={len(observed_contract)}")


if __name__ == "__main__":
    main()
