"""Extract a fixed two-pair, two-direction development subset; author labels stay evaluator-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from fetch_core4d_development_subset import ConcatRangeReader

PART = {
    "url": "https://zenodo.org/records/7767535/files/Bimanual%20Handovers%20Dataset.zip?download=1",
    "size": 8903684694,
    "md5": "971b57318f42c8c91fd35cb97f269892",
}
SEQUENCES = ("P07_P08_double_bag", "P08_P07_double_bag", "P09_P10_double_bag", "P10_P09_double_bag")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    r = ConcatRangeReader([PART], a.cache, budget=64 * 1024 * 1024)
    receipts = []
    prefix = "Bimanual Handovers Dataset/"
    with zipfile.ZipFile(r) as z:
        members = [(prefix + "ReadMe.txt", "evaluator/author-readme.txt")]
        for index, seq in enumerate(SEQUENCES, 1):
            opaque = f"clip-{index:04d}"
            pair = "_".join(sorted(seq.split("_")[:2]))
            for camera in (1, 2):
                folder = prefix + f"{pair}/Kinect_{camera}/"
                members.append((folder + seq + ".mp4", f"raw/{opaque}/camera-{camera}.mp4"))
                members.append(
                    (
                        folder + seq + "_Depth_Timestamps.csv",
                        f"evaluator/{opaque}/camera-{camera}-depth-timestamps.csv",
                    )
                )
            members.append(
                (
                    prefix + f"{pair}/OptiTrack_Global_Frame/{seq}.csv",
                    f"evaluator/{opaque}/author-motion-phases.csv",
                )
            )
        for name, dest in members:
            info = z.getinfo(name)
            if not 0 < info.file_size <= 16 * 1024 * 1024:
                raise ValueError("selected member is empty or exceeds budget")
            payload = z.read(info)  # zipfile verifies member CRC
            path = a.output / dest
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            receipts.append(
                dict(
                    member=name,
                    local_path=dest,
                    bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    crc32=info.CRC,
                )
            )
    result = dict(
        record="https://zenodo.org/records/7767535",
        archive=PART,
        full_archive_md5_verified=False,
        range_bytes=r.downloaded,
        selection="first two participant pairs, bag, both directions/cameras; development only",
        receipts=receipts,
        author_phase_kind="motion_threshold_proxy_not_contact_gold",
        semantic_transitions=0,
    )
    (a.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
