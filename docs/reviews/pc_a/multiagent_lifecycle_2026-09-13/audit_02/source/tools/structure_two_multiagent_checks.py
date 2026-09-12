"""Save two author-audit rounds with immutable logs and exact source snapshots."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = [
        ROOT / "src/cpswm/data_preflight/agent_roster.py",
        Path(__file__),
        *sorted((ROOT / "tests").glob("test_structure_two_agent_roster_round*.py")),
    ]
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for p in files:
        target = args.output / "source" / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    results = []
    for round_id in (1, 2):
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            f"tests/test_structure_two_agent_roster_round{round_id}.py",
        ]
        run = subprocess.run(
            command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (args.output / f"round{round_id}.log").write_text(run.stdout)
        print(run.stdout, flush=True)
        results.append({"round": round_id, "command": command, "returncode": run.returncode})
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (args.output / "receipt.json").write_text(
        json.dumps(
            {
                "scope": "two author unit-adversarial rounds, not independent PC-B or simulator acceptance",
                "python": sys.version,
                "source_before": before,
                "source_after": after,
                "source_unchanged": before == after,
                "rounds": results,
            },
            indent=2,
        )
    )
    return int(before != after or any(r["returncode"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
