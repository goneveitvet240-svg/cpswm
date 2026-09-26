"""Serial, fixed-source two-review validation with inspectable command receipts."""

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AUDIT = Path(__file__).resolve().parent


def source_state():
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT).decode()
    rows = {}
    for line in tree.splitlines():
        metadata, name = line.split("\t", 1)
        if not name.endswith(".py") or not name.startswith(
            ("src/", "tests/", "tools/", "docs/reviews/pc_a/")
        ):
            continue
        raw = (ROOT / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != metadata.split()[2]:
            raise ValueError(f"working source differs from frozen Git object: {name}")
        rows[name] = hashlib.sha256(raw).hexdigest()
    return rows


def run(main, output):
    output.mkdir(parents=True, exist_ok=False)
    baseline = source_state()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    receipts = []
    (output / "source-before.json").write_text(json.dumps(baseline, indent=2) + "\n")

    def command(name, arguments, allow_failure=False):
        if source_state() != baseline:
            raise ValueError("source drift before command")
        started = datetime.now(UTC).isoformat()
        tick = time.monotonic()
        with (output / f"{name}.log").open("wb") as stream:
            result = subprocess.run(arguments, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        receipt = {
            "name": name,
            "argv": [str(a) for a in arguments],
            "started_utc": started,
            "seconds": time.monotonic() - tick,
            "exit_code": result.returncode,
        }
        receipts.append(receipt)
        (output / "commands.json").write_text(
            json.dumps({"source_sha": sha, "commands": receipts}, indent=2) + "\n"
        )
        print(json.dumps(receipt), flush=True)
        if source_state() != baseline:
            raise ValueError("source drift during command")
        if result.returncode and not allow_failure:
            raise RuntimeError(f"validation failed: {name}; see preserved output")

    python = str(ROOT / ".venv/bin/python")
    command(
        "round1",
        [
            python,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            str(AUDIT / "audit_round1.py"),
            "tests/test_attention_workspace.py",
            "docs/reviews/pc_a/full_support_compute_2026-09-26/audit_round1.py",
            "tests/test_full_support_compute.py",
            "tests/test_proposal_execution_derivation.py",
            "tests/test_typed_proposal_training.py",
            "tests/test_proposal_inference_session.py",
            "tests/test_runtime_candidates.py",
            "tests/test_conditioned_inference_session.py",
            "tests/test_conditioned_proposal_runtime.py",
            "tests/test_proposal_decoder.py",
            "tests/test_proposal_learning.py",
        ],
    )
    command(
        "round2",
        [
            python,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            str(AUDIT / "audit_round2.py"),
            "docs/reviews/pc_a/full_support_compute_2026-09-26/audit_round2.py",
            "tests/test_proposal_execution_derivation.py",
        ],
    )
    command("mypy", [str(ROOT / ".venv/bin/mypy"), "--no-incremental"])
    command("ruff", [str(ROOT / ".venv/bin/ruff"), "check", "src", "tests", "tools", str(AUDIT)])
    original = main / "output/joint-audit-next-20260925/round2/training"
    derived = output / "derived"
    command(
        "derive",
        [
            python,
            "tools/derive_proposal_execution.py",
            "--training",
            str(original),
            "--output",
            str(derived),
            "--max-nodes",
            "65536",
        ],
    )
    for arm in (
        "typed_factor_graph_transformer",
        "slot_conditioned_perceiver",
        "autoregressive_typed_graph_policy",
    ):
        command(
            f"full-{arm}",
            [
                python,
                str(AUDIT.parent / "full_support_compute_2026-09-26/run_complete_support.py"),
                "--original",
                str(original),
                "--derived",
                str(derived),
                "--arm",
                arm,
                "--output",
                str(output / f"full-{arm}"),
            ],
        )
    legacy = output / "legacy-profile"
    command(
        "derive-legacy",
        [
            python,
            "tools/derive_proposal_execution.py",
            "--training",
            str(original),
            "--output",
            str(legacy),
        ],
    )
    command(
        "legacy-real-rejection",
        [
            python,
            str(AUDIT / "run_resource_rejection.py"),
            "--training",
            str(legacy),
            "--inputs",
            str(main / "output/full-support-compute-20260926/final-03/video-0003"),
            "--output",
            str(output / "legacy-real-rejection"),
        ],
    )
    for clip in range(1, 5):
        video = (
            main
            / f"output/datasets/bimanual-phase-four-clips-20260920/raw/clip-{clip:04d}/camera-1.mp4"
        )
        command(
            f"video-{clip:04d}",
            [
                python,
                "tools/run_runtime_candidate_video.py",
                "--video",
                str(video),
                "--weights",
                str(
                    main / "output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"
                ),
                "--training",
                str(derived),
                "--output",
                str(output / f"video-{clip:04d}"),
                "--frames",
                "4",
            ],
            allow_failure=True,
        )
    (output / "source-after.json").write_text(json.dumps(source_state(), indent=2) + "\n")
    if any(r["exit_code"] for r in receipts):
        raise RuntimeError("one or more fixed matrix commands failed; no complete acceptance")
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(baseline)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run(args.main, args.output.resolve())
