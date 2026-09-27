"""Second enrolled train video; source-rebuilt complete diagnostic, not a holdout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cpswm.data_preflight.full_hfd_training import packet_inventory
from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.visor_candidate_alignment import sha
from cpswm.data_preflight.visor_contact_supervision import ENROLLED_SOURCES, _derive
from cpswm.data_preflight.visor_pixel_supervision import AXES, compile_targets

VIDEO = "P01_03"
SOURCES = (
    ("P01_03.json", "704b5127036610db970bb3602205efd794df4e6bcd0bc86d337f22c903c009b4"),
    ("P01_03.zip", "5bd406deeb77b575d350e96c1b3a509b2a90bc9413c2fdbb95e34da9e4aae149"),
    *ENROLLED_SOURCES[2:],
)


def derive_component(root: Path) -> dict[str, Any]:
    before = packet_inventory(root)
    if set(before) != {name for name, _ in SOURCES}:
        raise ValueError("diagnostic source inventory differs")
    source = {}
    for name, digest in SOURCES:
        raw = (root / name).read_bytes()
        if sha(raw) != digest:
            raise ValueError("diagnostic source differs from enrolled author bytes")
        source[name] = raw
    if before != packet_inventory(root):
        raise ValueError("diagnostic sources changed during read")
    original = _derive(source, video=VIDEO)
    targets = compile_targets(original)
    manifest = strict_json(targets["manifest.json"])
    return {
        "inputs": [(r["input"], original[r["input"]["rgb"]]) for r in manifest["rows"]],
        "targets": [{axis: targets[r["targets"][axis]] for axis in AXES} for r in manifest["rows"]],
        "manifest_sha256": sha(targets["manifest.json"]),
        "pixel_manifest": targets["manifest.json"],
        "source_report": strict_json(original["manifest.json"])["report"],
        "summary": manifest["summary"],
        "source_pins": dict(SOURCES),
    }


def require_disjoint(
    train: list[tuple[dict[str, Any], bytes]], diagnostic: list[tuple[dict[str, Any], bytes]]
) -> None:
    if not train or len(diagnostic) < 2:
        raise ValueError("nonempty training and complete diagnostic required")
    for field in ("rgb_sha256", "pixel_sha256"):
        a = {r[field] for r, _ in train}
        b = {r[field] for r, _ in diagnostic}
        if a & b:
            raise ValueError("training and diagnostic images overlap")
