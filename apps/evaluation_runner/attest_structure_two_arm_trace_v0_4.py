#!/usr/bin/env python3
"""Custodian-only signer for one completed Structure-Two v0.4 arm trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cpswm.system.attestation import Ed25519AttestationSigner  # noqa: E402
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (  # noqa: E402
    EXPECTED_ARMS,
    compute_producer_source_bundle,
    produce_arm_prediction_rows,
)
from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_4 import (  # noqa: E402
    make_bound_arm_trace_payload,
    write_bound_arm_trace,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (  # noqa: E402
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_4 import (  # noqa: E402
    load_preregistered_freeze_authorization,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (  # noqa: E402
    DEFAULT_DRAFT,
    DEFAULT_MANIFEST,
    load_frozen_validation_gate_design,
    verify_validation_gate_report,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_4 import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_GATE_A_OUTPUT,
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run only in the external custodian environment after Gate A passes."
    )
    parser.add_argument("--unsigned-trace", type=Path, required=True)
    parser.add_argument("--private-key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise FileExistsError("signed arm trace already exists; refusing to overwrite")
    trusted_key_id, trusted_public_key_sha256, _ = load_preregistered_freeze_authorization(
        ROOT / DEFAULT_DRAFT
    )
    signer = Ed25519AttestationSigner.from_private_key_pem(
        key_id=args.key_id,
        private_key_pem=args.private_key_file.read_bytes(),
    )
    if signer.key_id != trusted_key_id or (
        signer.verifier().public_key_sha256 != trusted_public_key_sha256
    ):
        raise ValueError("arm-trace signer differs from the preregistered trust anchor")

    gate_a = verify_validation_gate_report(
        ROOT / DEFAULT_GATE_A_OUTPUT,
        repository_root=ROOT,
        recompute=True,
    )
    if gate_a.get("gate_a_passed") is not True:
        raise ValueError("Gate A did not pass; arm traces may not be signed")
    manifest_sha256 = _file_sha256(ROOT / DEFAULT_MANIFEST)
    unsigned = json.loads(args.unsigned_trace.read_text(encoding="utf-8"))
    arm = str(unsigned["arm"])
    if arm not in EXPECTED_ARMS:
        raise ValueError("unsigned trace arm is outside the frozen v0.4 set")
    if unsigned.get("gate_a_content_sha256") != gate_a["content_sha256"]:
        raise ValueError("unsigned trace is bound to the wrong Gate A artifact")
    if unsigned.get("manifest_sha256") != manifest_sha256:
        raise ValueError("unsigned trace is bound to the wrong frozen manifest")
    source_bundle = compute_producer_source_bundle(ROOT)
    if unsigned.get("producer_source_bundle_sha256") != source_bundle.content_sha256:
        raise ValueError("unsigned trace names a producer source bundle not present here")

    # A signature over candidate-supplied bytes alone proves integrity but not
    # that the bytes came from the frozen adapter.  The custodian therefore
    # regenerates this arm from the signed manifest and verified Gate-A rollout
    # order before signing anything.
    design = load_frozen_validation_gate_design(
        ROOT / DEFAULT_MANIFEST,
        repository_root=ROOT,
    )
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    generated = []
    regenerated_contract: list[tuple[str, int]] = []
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
                regenerated_contract.append((rollout.rollout_id, len(rollout.steps)))
    gate_a_contract = [
        (str(item["rollout_id"]), int(item["scored_step_count"]))
        for item in gate_a["ordered_scored_rollouts"]
    ]
    if regenerated_contract != gate_a_contract:
        raise ValueError("custodian-regenerated rollout contract differs from Gate A")
    expected_rows = produce_arm_prediction_rows(generated, arms=(arm,))[arm]
    supplied_rows = tuple(
        (str(row[0]), tuple(str(item) for item in row[1]))
        for row in unsigned["episode_predictions"]
    )
    if supplied_rows != expected_rows:
        raise ValueError("unsigned trace differs from custodian recomputation")
    payload = make_bound_arm_trace_payload(
        arm=arm,
        gate_a_content_sha256=str(unsigned["gate_a_content_sha256"]),
        manifest_sha256=str(unsigned["manifest_sha256"]),
        producer_run_id=str(unsigned["producer_run_id"]),
        producer_source_bundle_sha256=str(unsigned["producer_source_bundle_sha256"]),
        episode_predictions=supplied_rows,
        signer=signer,
    )
    write_bound_arm_trace(payload, output)
    print(f"signed_trace={output}")
    print(f"arm={payload['arm']}")
    print(f"content_sha256={payload['content_sha256']}")


if __name__ == "__main__":
    main()
