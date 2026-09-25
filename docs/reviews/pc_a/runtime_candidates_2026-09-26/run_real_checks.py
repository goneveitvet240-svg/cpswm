"""Fixed four video prefixes, three unselected checkpoint arms, exact source binding."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=False)


def hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "tests", "tools")
        for p in sorted((ROOT / folder).rglob("*.py"))
    }


before = hashes()
report = {
    "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "source_files": before,
    "runs": [],
    "independent_auditors": 0,
    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
for index in range(1, 5):
    clip = f"clip-{index:04d}"
    command = [
        str(ROOT / ".venv/bin/python"),
        "tools/run_runtime_candidate_video.py",
        "--video",
        str(DATA / "datasets/bimanual-phase-four-clips-20260920/raw" / clip / "camera-1.mp4"),
        "--weights",
        str(DATA / "models/torchvision/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"),
        "--training",
        str(DATA / "joint-audit-next-20260925/round2/training"),
        "--output",
        str(OUT / clip),
    ]
    with (OUT / f"{clip}.log").open("w") as log:
        run = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    report["runs"].append({"clip": clip, "argv": command, "exit_code": run.returncode})
    print(clip, run.returncode, flush=True)
report["source_unchanged"] = before == hashes()
report["all_passed"] = report["source_unchanged"] and all(
    r["exit_code"] == 0 for r in report["runs"]
)
(OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
raise SystemExit(0 if report["all_passed"] else 1)
