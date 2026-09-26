"""Check every real conditional role and preserve the unresolved-person denominator."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

source, output = map(Path, sys.argv[1:])
raw = source.read_bytes()
data = json.loads(raw)
pairs_total, roles_total, role_frames = 0, 0, []
ious = []
for row in data["records"]:
    interaction = row["interaction"]
    pairs = {p["pair_id"]: p for p in interaction["person_identity_pairs"]}
    assert len(pairs) == len(interaction["person_identity_pairs"])
    pairs_total += len(pairs)
    for p in pairs.values():
        assert p["hypotheses"] == ["same_person_multiple_detections", "distinct_people"]
        assert p["status"] == "UNRESOLVED_GEOMETRY_ONLY"
        assert p["observation_id"] == row["visual"]["observation_id"]
    for role in interaction["role_alternatives"]:
        pair = pairs[role["identity_pair_id"]]
        assert set(pair["track_ids"]) == {role["actor_track_id"], role["recipient_track_id"]}
        assert role["required_identity_hypothesis"] == "distinct_people"
        assert role["explanation"].startswith("conditional_")
        ious.append(pair["box_iou"])
        roles_total += 1
    assert not interaction["memory_write_authorized"]
    if interaction["role_alternatives"]:
        role_frames.append(
            {
                "key": row["key"],
                "roles": len(interaction["role_alternatives"]),
                "pairs": list(pairs.values()),
            }
        )
assert all(
    w["core_ledger_unchanged"] and w["perception_restore_equal"] and w["execution_traces"] == 0
    for w in data["windows"]
)
assert (
    data["memory_writes"] == data["executed_actions"] == data["natural_semantic_publications"] == 0
)
summary = {
    "source_result_sha256": hashlib.sha256(raw).hexdigest(),
    "frames": len(data["records"]),
    "windows": len(data["windows"]),
    "person_identity_pairs": pairs_total,
    "conditional_roles": roles_total,
    "role_positive_frames": len(role_frames),
    "unconditional_roles": 0,
    "role_pair_iou_range": [min(ious), max(ious)] if ious else [],
    "pair_status": dict(
        Counter(
            p["status"] for r in data["records"] for p in r["interaction"]["person_identity_pairs"]
        )
    ),
    "role_frames": role_frames,
    "natural_identity_calibration": False,
    "pairwise_not_joint_identity_partition": True,
    "new_training_steps": 0,
    "memory_writes": 0,
    "executed_actions": 0,
    "limitation": "Identity alternatives are unweighted. No claim of resolving duplicate people.",
}
output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "role_frames"}))
