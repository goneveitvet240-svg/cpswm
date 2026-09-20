"""Fetch the fixed 3x60-frame HO-Cap development subset without full archives.

Official links: https://irvlutd.github.io/HOCap/ and IRVLUTD/HO-Cap
config/hocap_recordings.yaml at 576c63ebf3b84dfec8744ba0f021234213bf0dab.
The public app.box.com hostname serves the same author share identifiers; the
university vanity hostname timed out locally. No passwords or cookies are used.
Dataset: CC BY 4.0, Wang et al., HO-Cap, NeurIPS 2025.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from dataclasses import asdict
from pathlib import Path

import yaml

from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource

SEQUENCES = ("20231027_112303", "20231027_113202", "20231027_113535")
CAMERA = "105322251564"
ARCHIVES = {
    "raw": "mutor2a09kudze1yw173gsfetsru7ces",
    "labels": "ayd4st2wo588z2yqbuxalptxnz2qxlj5",
    "poses": "2lofbp2yd005d8o213ns77mdrtxg8eep",
}


class RangeReader(io.RawIOBase):
    """Bounded explicit-range reader; ZIP validates every extracted member CRC."""

    def __init__(self, url: str, cache: Path, *, download_budget: int = 128 * 1024 * 1024):
        if not 0 < download_budget <= 512 * 1024 * 1024:
            raise ValueError("download budget must be within 512MiB per archive")
        self.download_budget = download_budget
        with urllib.request.urlopen(url, timeout=30) as response:
            self.resolved_url = response.url  # ephemeral public URL; never logged
            self.size = int(response.headers["Content-Length"])
            version = dict(
                source=url, size=self.size, modified=response.headers.get("Last-Modified")
            )
        cache.mkdir(parents=True, exist_ok=True)
        version_path = cache / "version.json"
        if version_path.exists() and json.loads(version_path.read_text()) != version:
            raise ValueError("remote archive version changed; use a fresh cache")
        version_path.write_text(json.dumps(version))
        self.cache, self.position, self.downloaded = cache, 0, 0
        self.block_size = 1024 * 1024

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("invalid seek mode")
        self.position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if self.position < 0:
            raise ValueError("negative range offset")
        return self.position

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.position + size, self.size)
        if end - self.position > 128 * 1024 * 1024:
            raise ValueError("single allocation exceeds 128MiB budget")
        chunks = []
        while self.position < end:
            start = self.position // self.block_size * self.block_size
            stop = min(start + self.block_size, self.size)
            path = self.cache / f"{start}-{stop}.bin"
            if path.exists():
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != path.with_suffix(".sha256").read_text():
                    raise ValueError("cached range changed")
            else:
                if self.downloaded + stop - start > self.download_budget:
                    raise ValueError("archive download exceeds declared budget")
                request = urllib.request.Request(
                    self.resolved_url, headers={"Range": f"bytes={start}-{stop - 1}"}
                )
                with urllib.request.urlopen(request, timeout=40) as response:
                    if (
                        response.status != 206
                        or response.headers["Content-Range"]
                        != f"bytes {start}-{stop - 1}/{self.size}"
                    ):
                        raise ValueError("server did not honor exact bounded range")
                    data = response.read(stop - start + 1)
                self.downloaded += len(data)
                if len(data) != stop - start:
                    raise ValueError("short or oversized range")
                path.write_bytes(data)
                path.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest())
            if len(data) != stop - start:
                raise ValueError("cached range length mismatch")
            high = min(end, stop)
            chunks.append(data[self.position - start : high - start])
            self.position = high
        return b"".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--windows", nargs="+", choices=("prefix", "midpoint", "suffix"), default=["prefix"]
    )
    parser.add_argument("--frame-count", type=int, default=60)
    parser.add_argument("--download-budget-mib", type=int, default=128)
    args = parser.parse_args()
    if not 1 <= args.frame_count <= 120 or len(set(args.windows)) != len(args.windows):
        parser.error("bounded frame count and unique windows required")
    indices = {}
    args.output.mkdir(parents=True, exist_ok=False)
    receipts, sources = [], []
    for lane, key in ARCHIVES.items():
        url = f"https://app.box.com/shared/static/{key}.zip"
        reader = RangeReader(
            url, args.cache / key, download_budget=args.download_budget_mib * 1024 * 1024
        )
        with zipfile.ZipFile(reader) as archive:
            selected = []
            for sequence in SEQUENCES:
                prefix = f"subject_5/{sequence}"
                if lane == "raw":
                    metadata = yaml.safe_load(archive.read(prefix + "/meta.yaml"))
                    total = metadata["num_frames"]
                    if type(total) is not int or total < args.frame_count:
                        raise ValueError("sequence shorter than requested window")
                    starts = {
                        "prefix": 0,
                        "midpoint": (total - args.frame_count) // 2,
                        "suffix": total - args.frame_count,
                    }
                    indices[sequence] = sorted(
                        {
                            i
                            for window in args.windows
                            for i in range(starts[window], starts[window] + args.frame_count)
                        }
                    )
                if lane == "poses":
                    selected.extend(
                        f"{prefix}/{p}" for p in ("poses_o.npy", "poses_m.npy", "poses_pv.npy")
                    )
                elif lane == "raw":
                    selected.append(prefix + "/meta.yaml")
                    selected.extend(
                        f"{prefix}/{CAMERA}/{kind}_{i:06d}.{ext}"
                        for i in indices[sequence]
                        for kind, ext in (("color", "jpg"), ("depth", "png"))
                    )
                else:
                    selected.extend(
                        f"{prefix}/{CAMERA}/label_{i:06d}.npz" for i in indices[sequence]
                    )
            for member in selected:
                info = archive.getinfo(member)
                if not 0 < info.file_size <= 4 * 1024 * 1024:
                    raise ValueError("unexpected subset member allocation")
                data = archive.read(info)
                dest_lane = "raw" if member.endswith((".jpg", ".png")) else "evaluator"
                path = args.output / dest_lane / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                receipts.append(
                    dict(
                        source=url,
                        member=member,
                        sha256=hashlib.sha256(data).hexdigest(),
                        bytes=len(data),
                        zip_crc32=info.CRC,
                    )
                )
        sources.append(
            dict(source=url, archive_size=reader.size, downloaded_bytes=reader.downloaded)
        )
        print(lane, "downloaded", reader.downloaded, flush=True)
    url = "https://app.box.com/shared/static/nlp4c6vtd0n8o0entxlh1vxdpcdeh0h8.zip"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("unexpected calibration package size")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if not name.startswith(
                ("calibration/intrinsics/", "calibration/extrinsics/")
            ) or not name.endswith(".yaml"):
                continue
            path = (args.output / name).resolve()
            if (
                not path.is_relative_to(args.output.resolve())
                or archive.getinfo(name).file_size > 65536
            ):
                raise ValueError("unexpected calibration member")
            payload = archive.read(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    by_member = {r["member"]: r for r in receipts}
    frames, annotations = [], []
    for sequence in SEQUENCES:
        seq = "subject_5/" + sequence
        for index in indices[sequence]:
            prefix = f"{seq}/{CAMERA}"
            rgb = by_member[f"{prefix}/color_{index:06d}.jpg"]
            depth = by_member[f"{prefix}/depth_{index:06d}.png"]
            label = by_member[f"{prefix}/label_{index:06d}.npz"]
            frames.append(
                asdict(HOCapFrameSource(seq, CAMERA, index, rgb["sha256"], depth["sha256"]))
            )
            annotations.append(
                dict(
                    sequence_id=seq,
                    camera_id=CAMERA,
                    frame_index=index,
                    member=label["member"],
                    annotation_sha256=label["sha256"],
                )
            )
    for filename, value in (
        ("raw_manifest.json", frames),
        ("annotation_manifest.json", annotations),
        ("download_receipts.json", receipts),
        ("archives.json", sources),
        (
            "sampling.json",
            dict(
                windows=args.windows,
                frame_count=args.frame_count,
                selection="metadata_only_fixed_windows_development_not_holdout",
                frame_indices=indices,
            ),
        ),
    ):
        path = args.output / filename
        path.write_text(json.dumps(value, indent=2) + "\n")
        print(filename, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
