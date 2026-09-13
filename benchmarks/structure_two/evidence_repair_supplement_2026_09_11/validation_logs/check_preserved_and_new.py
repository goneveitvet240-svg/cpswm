"""Compare preserved Git bytes and full scientific fields; does not claim a rerun."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BASE = "91dbdc57968071be29976d1a7b99de51d9288cdd"
SUPPLEMENT = Path("benchmarks/structure_two/evidence_repair_supplement_2026_09_11")
LEGACY = Path("benchmarks/structure_two/evidence_repair_2026_09_11")
NAMES = (
    "three_arm_death_test",
    "readout_posthoc_diagnostic",
    "debt_replay_confirmation",
    "readout_prior_factorial",
    "unseen_d0_holdout",
)


def original(relative: str) -> bytes:
    return subprocess.check_output(["git", "show", BASE + ":" + relative], cwd=ROOT)


def main() -> None:
    config = json.loads(
        original("configs/project_two_experiments/structure_two_evidence_history_v0_1.json")
    )
    paths = [row["path"] for row in config["entries"]]
    paths.extend(
        (LEGACY / "current" / f"structure_two_p5_{name}_v0_2.json").as_posix() for name in NAMES
    )
    paths.append((LEGACY / "historical_source_audit.json").as_posix())
    paths.extend(
        "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05/" + name
        for name in ("engineering_checkpoint.json", "engineering_audit_receipt.json")
    )
    preserved = []
    for relative in paths:
        raw = original(relative)
        if (ROOT / relative).read_bytes() != raw:
            raise ValueError("sealed reviewed bytes changed: " + relative)
        preserved.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
    prior_p0 = original("benchmarks/p0_checkpoint/content_manifest_v0_3.json")
    if (ROOT / SUPPLEMENT / "p0_reviewed_manifest_snapshot.json").read_bytes() != prior_p0:
        raise ValueError("archived reviewed P0 bytes changed")
    comparisons = []
    for name in NAMES:
        old_path = (LEGACY / "current" / f"structure_two_p5_{name}_v0_2.json").as_posix()
        new_path = SUPPLEMENT / "current_v0_3" / f"structure_two_p5_{name}_v0_3.json"
        old, new = json.loads(original(old_path)), json.loads((ROOT / new_path).read_bytes())
        excluded = {"source_binding", "evidence_context", "content_sha256"}
        a = {key: value for key, value in old.items() if key not in excluded}
        b = {key: value for key, value in new.items() if key not in excluded}
        if a != b:
            raise ValueError("scientific fields differ from reviewed v0.2: " + name)
        if new["evidence_context"]["artifact_version"] != "0.3":
            raise ValueError("new evidence artifact version mismatch")
        comparisons.append(
            {
                "name": name,
                "new_path": new_path.as_posix(),
                "new_content_sha256": new["content_sha256"],
                "all_scientific_fields_equal_to_reviewed_v0_2": True,
                "excluded_root_fields": sorted(excluded),
                "numerical_recomputation_claimed_by_this_byte_comparison": False,
            }
        )
    print(json.dumps({"preserved": preserved, "comparisons": comparisons}, indent=2))


if __name__ == "__main__":
    main()
