"""Recompute local evidence consistency; hashes are NOT source authentication."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/reviews/pc_a/multiagent_lifecycle_2026-09-13"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    rows = []
    for scene, count in (("ordinary", 1), ("ordinary", 2), ("procedural", 1), ("procedural", 2)):
        case = EVIDENCE / f"{scene}_{count}_wire_frozen_03"
        receipt = json.loads((case / "receipt.json").read_text())
        if not receipt["files_unchanged"] or receipt["files_before"] != receipt["files_after"]:
            raise ValueError("source changed during real execution")
        for name, digest in receipt["files_after"].items():
            if sha(Path(name)) != digest:
                raise ValueError(f"local source/runtime changed: {name}")
        if sha(case / "transport.jsonl") != receipt["trace_sha256"]:
            raise ValueError("trace was changed")
        trace = [json.loads(line) for line in (case / "transport.jsonl").read_text().splitlines()]
        sends = [x["payload"] for x in trace if x["kind"] == "send"]
        initialization = [x for x in sends if x["action"] == "Initialize"]
        if len(initialization) != 1 or initialization[0]["agentCount"] != count:
            raise ValueError("requested initialization not observed on wire")
        # Field 1 is a FULL raw Unity metadata packet, not an SDK-generated patch.
        raw_init = [
            x["metadata"]
            for x in trace
            if x["kind"] == "wire_payload"
            and x["field"] == 1
            and x["metadata"].get("sequenceId") == initialization[0]["sequenceId"]
            and all(a.get("lastAction") == "Initialize" for a in x["metadata"]["agents"])
        ]
        if len(raw_init) != 1:
            raise ValueError("full raw initialization packet is missing or ambiguous")
        actual = len(raw_init[0]["agents"])
        blocked = scene == "procedural" and count == 2
        if blocked:
            if (
                actual != 1
                or receipt.get("exception", {}).get("type") != "AgentRosterError"
                or sends[-1]["action"] != "Initialize"
                or any(
                    x["action"] in {"CreateHouse", "Pass", "RotateRight", "RotateLeft"}
                    for x in sends
                )
            ):
                raise ValueError("unsupported run was not stopped at initialization")
        else:
            if actual != count or receipt.get("exception") or receipt["observed_count"] != count:
                raise ValueError("legal control failed")
            checks = receipt["rotation_checks"]
            if len(checks) != count * 2 or not all(c["passed"] is True for c in checks):
                raise ValueError("rotation isolation incomplete")
            # Independently recompute positions/rotations from the retained raw trace.
            pending = None
            previous = None
            rotations = 0
            for entry in trace:
                if entry["kind"] == "send":
                    pending = entry["payload"]
                if entry["kind"] != "receive":
                    continue
                current = entry["metadata"]
                if pending and pending["action"] in {"RotateRight", "RotateLeft"}:
                    if current["sequenceId"] != pending["sequenceId"] or previous is None:
                        raise ValueError("rotation response not paired with request")
                    before = {a["agentId"]: a["agent"] for a in previous["agents"]}
                    after = {a["agentId"]: a["agent"] for a in current["agents"]}
                    if set(before) != set(after) or set(after) != set(range(count)):
                        raise ValueError("rotation changed roster")
                    for identity in before:
                        p, q = before[identity], after[identity]
                        if any(
                            abs(p["position"][k] - q["position"][k]) >= 0.002
                            for k in ("x", "y", "z")
                        ):
                            raise ValueError("rotation changed position")
                        delta = (
                            (90 if pending["action"] == "RotateRight" else -90)
                            if identity == pending["agentId"]
                            else 0
                        )
                        error = (q["rotation"]["y"] - p["rotation"]["y"] - delta + 180) % 360 - 180
                        if abs(error) >= 0.01 or any(
                            abs(p["rotation"][k] - q["rotation"][k]) >= 0.01 for k in ("x", "z")
                        ):
                            raise ValueError("rotation violated agent isolation")
                    rotations += 1
                previous = current
                pending = None
            if rotations != count * 2:
                raise ValueError("not all rotation transitions independently recomputed")
        rows.append(
            {
                "scene": scene,
                "requested": count,
                "actual_at_initialize": actual,
                "status": "BLOCKED_CORRECTLY_NOT_MULTIPLAYER_PASS" if blocked else "CONTROL_PASS",
            }
        )
    print(json.dumps(rows, indent=2))
    return rows


if __name__ == "__main__":
    rows = verify()
    target = EVIDENCE / "verification.json"
    with target.open("x") as stream:
        json.dump(
            {
                "head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "matrix": rows,
                "human_execution_verified": False,
                "full_joint_loop_verified": False,
            },
            stream,
            indent=2,
        )
    manifest = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted(EVIDENCE.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != "manifest.json"
    }
    with (EVIDENCE / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
