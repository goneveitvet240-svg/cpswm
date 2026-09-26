"""Freeze-bound sequential A audits, then actual import and fresh-source verification."""

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AUDIT = Path(__file__).resolve().parent


def sources():
    tree = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT).decode()
    state = {}
    for line in tree.splitlines():
        meta, name = line.split("\t", 1)
        if not name.endswith(".py") or not name.startswith(
            ("src/", "tests/", "tools/", "docs/reviews/pc_a/")
        ):
            continue
        raw = (ROOT / name).read_bytes()
        if (
            hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            != meta.split()[2]
        ):
            raise ValueError("working Python differs from Git: " + name)
        state[name] = hashlib.sha256(raw).hexdigest()
    return state


REUSED_SOURCE = "98c64b1df1008422c1af6f5056fb371edd9c96c9"
REUSED_PREDICTION = "7d654b5d2f574bd7a977b8fcd299605327ace6ab30e90b6768378453da5f2e47"


def verify_inference_unchanged():
    """Reuse only the exact measured artifact with unchanged inference code."""
    name = "src/cpswm/data_preflight/visor_candidate_alignment.py"
    old = subprocess.check_output(["git", "show", REUSED_SOURCE + ":" + name], cwd=ROOT)
    a, b = ast.parse(old), ast.parse((ROOT / name).read_bytes())

    # The only allowed changes in this module are the offline evaluator functions.
    def inference_nodes(tree):
        return [
            ast.dump(n)
            for n in tree.body
            if not (isinstance(n, ast.FunctionDef) and n.name in {"align_frame", "evaluate"})
        ]

    if inference_nodes(a) != inference_nodes(b):
        raise ValueError("inference module dependencies changed; rerun the model")
    changed = (
        subprocess.check_output(
            ["git", "diff", "--name-only", REUSED_SOURCE, "HEAD", "--", "src", "tools", "uv.lock"],
            cwd=ROOT,
        )
        .decode()
        .splitlines()
    )
    if changed != [name]:
        raise ValueError("other production dependencies changed; rerun the model")


def run(main, output, reuse_prediction=None):
    output.mkdir(parents=True, exist_ok=False)
    before = sources()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    (output / "source-before.json").write_text(json.dumps(before, indent=2) + "\n")
    receipts = []

    def command(name, argv):
        assert sources() == before
        started = datetime.now(UTC).isoformat()
        tick = time.monotonic()
        with (output / (name + ".log")).open("wb") as stream:
            result = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        row = {
            "name": name,
            "argv": argv,
            "started_utc": started,
            "seconds": time.monotonic() - tick,
            "exit_code": result.returncode,
        }
        receipts.append(row)
        (output / "commands.json").write_text(
            json.dumps({"source_sha": sha, "commands": receipts}, indent=2) + "\n"
        )
        assert sources() == before
        (output / "source-after.json").write_text(json.dumps(sources(), indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if result.returncode:
            raise RuntimeError("failed: " + name)

    python = sys.executable
    command(
        "round1",
        [
            python,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "tests/test_visor_candidate_alignment.py",
            "tests/test_visor_contact_supervision.py",
            "tests/test_natural_hands.py",
            "tests/test_hand_person_regions.py",
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
            str(AUDIT / "audit_second.py"),
            "tests/test_structure_two_continuous_input.py",
            "tests/test_continuous_state_recovery.py",
        ],
    )
    command("mypy", [python, "-m", "mypy", "--no-incremental"])
    command("ruff", [python, "-m", "ruff", "check", "src", "tests", "tools", str(AUDIT)])
    closed = main / "output/visor-contact-supervision-20260927/closed"
    source, packet = closed / "raw", closed / "final-02/packet"
    command(
        "source-verify",
        [
            python,
            "tools/prepare_visor_contact_supervision.py",
            "--source",
            str(source),
            "--output",
            str(packet),
            "--verify",
        ],
    )
    manifest_sha = hashlib.sha256((packet / "runtime/manifest.json").read_bytes()).hexdigest()
    prediction = output / "predictions.json"
    if reuse_prediction is None:
        command(
            "frontend",
            [
                python,
                "-u",
                "tools/run_visor_candidate_alignment.py",
                "infer",
                "--runtime",
                str(packet / "runtime"),
                "--manifest-sha256",
                manifest_sha,
                "--weights",
                str(
                    main / "output/models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"
                ),
                "--hand-model",
                str(main / "output/models/mediapipe/hand_landmarker-1.task"),
                "--output",
                str(prediction),
            ],
        )
    else:
        verify_inference_unchanged()
        command(
            "reuse-bound-prediction",
            [
                python,
                "-c",
                "import hashlib,sys; from pathlib import Path; "
                "raw=Path(sys.argv[1]).read_bytes(); "
                "assert hashlib.sha256(raw).hexdigest()==sys.argv[3]; "
                "f=Path(sys.argv[2]).open('xb'); f.write(raw); f.close(); "
                "print('Reused exact predictions from source '+sys.argv[4]+'; no fresh inference')",
                str(reuse_prediction),
                str(prediction),
                REUSED_PREDICTION,
                REUSED_SOURCE,
            ],
        )
    pin = hashlib.sha256(prediction.read_bytes()).hexdigest()
    (output / "execution-pin.json").write_text(
        json.dumps(
            {
                "source_sha": sha,
                "prediction_source_sha": REUSED_SOURCE if reuse_prediction else sha,
                "fresh_model_inference": reuse_prediction is None,
                "prediction_sha256": pin,
                "runtime_manifest_sha256": manifest_sha,
                "origin": "frozen local execution, not independent model attestation",
            },
            indent=2,
        )
    )
    result = output / "alignment.json"
    command(
        "alignment",
        [
            python,
            "tools/run_visor_candidate_alignment.py",
            "evaluate",
            "--source",
            str(source),
            "--packet",
            str(packet),
            "--prediction",
            str(prediction),
            "--prediction-sha256",
            pin,
            "--output",
            str(result),
        ],
    )
    command(
        "fresh-consumer",
        [
            python,
            "-c",
            "import json,sys; from pathlib import Path; "
            "from cpswm.data_preflight.visor_candidate_alignment import verify_alignment; "
            "r=verify_alignment(Path(sys.argv[1]),Path(sys.argv[2]),"
            "Path(sys.argv[3]),sys.argv[4],Path(sys.argv[5])); "
            "print(json.dumps(r['summary'],indent=2))",
            str(source),
            str(packet),
            str(prediction),
            pin,
            str(result),
        ],
    )
    print(
        json.dumps({"complete": True, "source_sha": sha, "source_files": len(before)}), flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-prediction", type=Path)
    args = parser.parse_args()
    run(args.main.resolve(), args.output.resolve(), args.reuse_prediction)
