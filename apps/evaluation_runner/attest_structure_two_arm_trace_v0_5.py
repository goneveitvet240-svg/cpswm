#!/usr/bin/env python3
"""Externally recompute and sign one v0.5 arm trace."""

from __future__ import annotations

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
    produce_arm_prediction_rows,
)
from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_5 import (  # noqa: E402
    make_bound_arm_trace_payload_v0_5,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (  # noqa: E402
    StructureTwoWorldGeneratorV02,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (  # noqa: E402
    compute_v0_5_source_bundle,
    load_preregistered_v0_5_authorization,
)
from cpswm.system.evaluation_operations.structure_two_world_validation_gate_v0_5 import (  # noqa: E402
    DEFAULT_DRAFT,
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    load_frozen_validation_gate_design_v0_5,
    verify_validation_gate_report_v0_5,
)


def main() -> None:
    if len(sys.argv) != 9:
        raise SystemExit(
            "usage: attest ... --unsigned TRACE --private-key KEY --key-id ID --output OUT"
        )
    args = dict(zip(sys.argv[1::2], sys.argv[2::2], strict=True))
    unsigned_path = Path(args["--unsigned"])
    output = Path(args["--output"])
    if output.exists():
        raise FileExistsError("signed v0.5 trace exists")
    key_id, public_hash, _ = load_preregistered_v0_5_authorization(ROOT / DEFAULT_DRAFT)
    signer = Ed25519AttestationSigner.from_private_key_pem(
        key_id=args["--key-id"],
        private_key_pem=Path(args["--private-key"]).read_bytes(),
    )
    if signer.key_id != key_id or signer.verifier().public_key_sha256 != public_hash:
        raise ValueError("v0.5 trace signer differs from trust anchor")
    gate_a = verify_validation_gate_report_v0_5(
        ROOT / DEFAULT_OUTPUT, repository_root=ROOT, recompute=True
    )
    supplied = json.loads(unsigned_path.read_text(encoding="utf-8"))
    arm = str(supplied["arm"])
    if arm not in EXPECTED_ARMS:
        raise ValueError("v0.5 trace arm is outside the frozen set")
    design = load_frozen_validation_gate_design_v0_5(ROOT / DEFAULT_MANIFEST, repository_root=ROOT)
    generator = StructureTwoWorldGeneratorV02(design.distribution)
    generated = []
    for seed in design.validation_world_seeds:
        world = generator.sample_world(seed)
        for trajectory_seed in design.trajectory_seeds:
            for observation_seed in design.observation_seeds:
                generated.append(
                    (
                        world,
                        generator.generate_rollout(
                            world,
                            trajectory_seed=trajectory_seed,
                            observation_seed=observation_seed,
                        ),
                    )
                )
    expected_rows = produce_arm_prediction_rows(generated, arms=(arm,))[arm]
    supplied_rows = tuple(
        (str(row[0]), tuple(str(item) for item in row[1]))
        for row in supplied["episode_predictions"]
    )
    if supplied_rows != expected_rows:
        raise ValueError("v0.5 supplied trace differs from custodian recomputation")
    source = compute_v0_5_source_bundle(ROOT)
    if supplied["producer_source_bundle_sha256"] != source.content_sha256:
        raise ValueError("v0.5 supplied trace names the wrong source bundle")
    payload = make_bound_arm_trace_payload_v0_5(
        arm=arm,
        gate_a_content_sha256=gate_a["content_sha256"],
        manifest_sha256=str(supplied["manifest_sha256"]),
        producer_run_id=str(supplied["producer_run_id"]),
        producer_source_bundle_sha256=source.content_sha256,
        episode_predictions=supplied_rows,
        signer=signer,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"signed_trace={output}")
    print(f"arm={arm}")


if __name__ == "__main__":
    main()
