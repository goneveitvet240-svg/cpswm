"""Fetch matching author alignment/object poses to an evaluator-only directory.

Never loads pickled human motion files or supplies author poses to inference.
Partial ZIP reads verify CRC; full archive LFS SHA is not verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from fetch_core4d_development_subset import REVISION, ConcatRangeReader, get_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        choices=("https://huggingface.co", "https://hf-mirror.com"),
        default="https://huggingface.co",
    )
    parser.add_argument("--sequence", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= len(args.sequence) <= 4 or any(
        re.fullmatch(r"\d{8}(?:_\d)?/\d{3}", s) is None for s in args.sequence
    ):
        parser.error("one to four explicit CORE4D sequence identities required")
    args.output.mkdir(parents=True, exist_ok=False)
    url = f"{args.endpoint}/api/datasets/leolyliu/CORE4D/tree/{REVISION}/CORE4D_Real"
    tree = get_json(url)
    receipts = []
    archives = []
    for name in ("human_object_motions.zip", "camera_parameters.zip"):
        meta = next(p for p in tree if p["path"] == "CORE4D_Real/" + name)
        part = dict(
            path=meta["path"],
            size=meta["size"],
            lfs_sha256=meta["lfs"]["oid"],
            url=f"{args.endpoint}/datasets/leolyliu/CORE4D/resolve/{REVISION}/" + meta["path"],
        )
        reader = ConcatRangeReader([part], args.cache / name, budget=64 * 1024 * 1024)
        with zipfile.ZipFile(reader) as archive:
            names = archive.namelist()
            for seq in args.sequence:
                if name == "human_object_motions.zip":
                    wanted = [
                        next(n for n in names if n.endswith("/" + seq + "/" + leaf))
                        for leaf in (
                            "smooth_objposes.npy",
                            "object_metadata.json",
                            "aligned_frame_ids.txt",
                        )
                    ]
                else:
                    wanted = sorted(
                        n
                        for n in names
                        if "/" + seq.split("/")[0] + "/" in "/" + n and n.endswith(".txt")
                    )
                for member in wanted:
                    if any(r["archive"] == name and r["member"] == member for r in receipts):
                        continue
                    info = archive.getinfo(member)
                    if not 0 < info.file_size <= 8 * 1024 * 1024:
                        raise ValueError("supervision member exceeds budget")
                    path = (args.output / member).resolve()
                    if not path.is_relative_to(args.output.resolve()):
                        raise ValueError("member escaped output")
                    payload = archive.read(info)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                    receipts.append(
                        dict(
                            archive=name,
                            member=member,
                            sha256=hashlib.sha256(payload).hexdigest(),
                            bytes=len(payload),
                            zip_crc32=info.CRC,
                        )
                    )
            archives.append(dict(**part, new_range_bytes=reader.downloaded))
    result = dict(
        revision=REVISION,
        sequences=args.sequence,
        archives=archives,
        receipts=receipts,
        lane="evaluator_only",
        human_pickle_loaded=False,
        full_archive_sha_verified=False,
    )
    (args.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
