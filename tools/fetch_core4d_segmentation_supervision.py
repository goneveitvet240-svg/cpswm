"""Extract two camera1 author masks to the evaluator-only lane; no pickle loads."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from fetch_core4d_development_subset import REVISION, ConcatRangeReader


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    part = dict(
        path="CORE4D_Real/human_object_segmentations.zip",
        size=869304639,
        lfs_sha256="9db384c5f093a923eb804e0e946367b434a30b5e326995a371c2ec71b0e1d974",
        url=f"https://hf-mirror.com/datasets/leolyliu/CORE4D/resolve/{REVISION}/CORE4D_Real/human_object_segmentations.zip",
    )
    reader = ConcatRangeReader([part], a.cache, budget=64 * 1024 * 1024)
    rows = []
    with zipfile.ZipFile(reader) as archive:
        (a.output / "members.json").write_text(
            json.dumps(
                [
                    {"name": i.filename, "size": i.file_size, "compressed": i.compress_size}
                    for i in archive.infolist()
                ],
                indent=2,
            )
            + "\n"
        )
        for seq in ("20231002/023", "20231002/024"):
            member = next(
                n for n in archive.namelist() if n.endswith("/" + seq + "/camera1_mask.npz")
            )
            info = archive.getinfo(member)
            if not 0 < info.file_size < 32 * 1024 * 1024:
                raise ValueError("bounded mask archive required")
            payload = archive.read(info)
            dest = a.output / (seq.replace("/", "_") + "-camera1_mask.npz")
            dest.write_bytes(payload)
            with zipfile.ZipFile(io.BytesIO(payload)) as inner:
                arrays = [
                    dict(name=i.filename, bytes=i.file_size, compressed=i.compress_size)
                    for i in inner.infolist()
                ]
            rows.append(
                dict(
                    sequence=seq,
                    member=member,
                    file=dest.name,
                    bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    crc32=info.CRC,
                    arrays=arrays,
                )
            )
    result = dict(
        revision=REVISION,
        archive=part,
        range_bytes=reader.downloaded,
        full_archive_sha_verified=False,
        lane="evaluator_only",
        pickle_loaded=False,
        receipts=rows,
    )
    (a.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
