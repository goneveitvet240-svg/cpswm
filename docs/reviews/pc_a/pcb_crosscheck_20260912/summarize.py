"""Validate shared B manifest and summarize independently observed consequences."""

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
B = "9195dd4b3872cbf770bd73ad4c84cca007137c3d"
BASE = "1bd513f51ab7e54a7290870a5f34b524254d55c6"
PREFIX = "docs/reviews/data/pc_b_w3_r6_independent_20260912/"


def blob(name):
    return subprocess.check_output(["git", "show", B + ":" + name], cwd=REPO)


manifest = blob(PREFIX + "manifest.sha256").decode()
checked = []
for line in manifest.splitlines():
    if not line.strip():
        continue
    digest, name = line.split(None, 1)
    name = name.strip().lstrip("*")
    assert hashlib.sha256(blob(name)).hexdigest() == digest.lower(), name
    checked.append(name)
changes = subprocess.check_output(
    ["git", "diff", "--name-only", BASE, B], cwd=REPO, text=True
).splitlines()
assert len(changes) == 21
assert not any(p.startswith(("src/", "apps/", "tools/", "configs/")) for p in changes)
result = {"b_manifest_verified_files": len(checked), "b_changed_files": changes, "versions": {}}
for label in ("r6", "r7"):
    command = json.loads((OUT / (label + ".command.json")).read_text())
    cases = list(ET.parse(OUT / (label + ".xml")).getroot().iter("testcase"))
    failed = [c.attrib["name"] for c in cases if c.find("failure") is not None]
    assert len(cases) == 6 and len(failed) == 5
    assert all(
        "DID NOT RAISE" in c.find("failure").attrib.get("message", "")
        for c in cases
        if c.find("failure") is not None
    )
    raw = json.loads((OUT / (label + "_observations.stdout.log")).read_text())
    rows = []
    for c in raw["cases"]:
        initial, pre, after = c["initial"], c["pre_attack"], c["after"]
        marginal = after["marginal"]
        probabilities = marginal.get("probabilities", {})
        original = set(initial["core_locations"])
        extras = {k: v for k, v in probabilities.items() if k not in original}
        orphan_count = sum(
            len(set(body["statistic_particle_ids"]) - set(body["receipt_particle_ids"]))
            for body in after["input_bodies"].values()
        )
        assert c["call"]["status"] == "ACCEPTED_OR_RETURNED"
        assert c["ledger_head_unchanged_during_public_call"]
        rows.append(
            dict(
                id=c["id"],
                call=c["call"],
                foreign_probabilities=extras,
                records_before=len(pre["record_particle_ids"]),
                records_after=len(after["record_particle_ids"]),
                orphan_statistics_in_body=orphan_count,
                readout_disjoint_current_support=bool(probabilities)
                and not set(probabilities).intersection(after["core_locations"]),
                semantic_changed=c["semantic_identity_changed_during_public_call"],
                ledger_unchanged=c["ledger_head_unchanged_during_public_call"],
            )
        )
    result["versions"][label] = dict(
        tested_sha=command["tested_sha"],
        overlay_sha256=command["overlay_sha256"],
        passed=1,
        failed=failed,
        consequences=rows,
        unchanged_recorder_embedded_sha=raw["tested_sha"],
    )
assert result["versions"]["r6"]["overlay_sha256"] == result["versions"]["r7"]["overlay_sha256"]
(OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
