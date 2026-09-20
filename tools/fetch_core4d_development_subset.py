"""Bounded public CORE4D development extraction from concatenated ZIP parts.

Author repository: https://github.com/leolyliu/CORE4D-Instructions
Mirror transport is explicit. Partial downloads verify range lengths and ZIP CRC,
not full LFS object SHA256. Author annotations never enter the raw lane.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REVISION = "81bb2bb876a4a54ac94e67c788d7c31364f1c43e"
REPOSITORY = "leolyliu/CORE4D"


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = response.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("metadata exceeds budget")
    return json.loads(payload)


class ConcatRangeReader(io.RawIOBase):
    """Seek in a concatenated archive without allocating or downloading it all."""

    def __init__(self, parts, cache, *, budget=192 * 1024 * 1024, fetch=None):
        if not parts or not 0 < budget <= 512 * 1024 * 1024:
            raise ValueError("bounded nonempty archive required")
        if any(type(p["size"]) is not int or p["size"] <= 0 for p in parts):
            raise ValueError("invalid part size")
        self.parts, self.cache, self.budget = parts, Path(cache), budget
        self.size = sum(p["size"] for p in parts)
        self.position = self.downloaded = 0
        self.block_size = 256 * 1024
        self.fetch = fetch or self._fetch
        self.cache.mkdir(parents=True, exist_ok=True)
        identity = self.cache / "identity.json"
        description = json.dumps(parts, sort_keys=True)
        if identity.exists() and identity.read_text() != description:
            raise ValueError("cache archive identity changed")
        identity.write_text(description)

    @staticmethod
    def _fetch(part, start, end):
        request = urllib.request.Request(part["url"], headers={"Range": f"bytes={start}-{end - 1}"})
        with urllib.request.urlopen(request, timeout=40) as response:
            if (
                response.status != 206
                or response.headers.get("Content-Range")
                != f"bytes {start}-{end - 1}/{part['size']}"
            ):
                raise ValueError("server did not honor exact range")
            return response.read(end - start + 1)

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("invalid whence")
        value = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if value < 0:
            raise ValueError("negative seek")
        self.position = value
        return value

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.position + size)
        if end - self.position > 64 * 1024 * 1024:
            raise ValueError("single read exceeds allocation budget")
        chunks = []
        while self.position < end:
            base = 0
            for index, part in enumerate(self.parts):  # noqa: B007 - used after break
                if self.position < base + part["size"]:
                    break
                base += part["size"]
            offset = self.position - base
            start = offset // self.block_size * self.block_size
            stop = min(start + self.block_size, part["size"])
            path = self.cache / f"{index}-{start}-{stop}.bin"
            if path.exists():
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != path.with_suffix(".sha256").read_text():
                    raise ValueError("cached range changed")
            else:
                if self.downloaded + stop - start > self.budget:
                    raise ValueError("download budget exceeded")
                data = self.fetch(part, start, stop)
                self.downloaded += len(data)
                if len(data) != stop - start:
                    raise ValueError("short or oversized range")
                if path.exists() and path.read_bytes() != data:
                    raise ValueError("existing extracted member differs from archive")
                path.write_bytes(data)
                path.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest())
            if len(data) != stop - start:
                raise ValueError("cached range size differs")
            high = min(end - base, stop)
            chunks.append(data[offset - start : high - start])
            self.position = base + high
        return b"".join(chunks)


def retain_text(path, text):
    if path.exists() and path.read_text() != text:
        raise ValueError("retained subset metadata differs")
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        choices=("https://huggingface.co", "https://hf-mirror.com"),
        default="https://huggingface.co",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--resume-incomplete", action="store_true")
    args = parser.parse_args()
    if args.resume_incomplete and (args.output / "manifest.json").exists():
        parser.error("completed subset cannot be resumed or overwritten")
    args.output.mkdir(parents=True, exist_ok=args.resume_incomplete)
    prefix = f"{args.endpoint}/datasets/{REPOSITORY}/resolve/{REVISION}/"
    trees = get_json(
        f"{args.endpoint}/api/datasets/{REPOSITORY}/tree/{REVISION}/CORE4D_Real/allocentric_RGB_videos"
    )
    parts = [
        {
            "path": p["path"],
            "size": p["size"],
            "lfs_sha256": p["lfs"]["oid"],
            "url": prefix + p["path"],
        }
        for p in sorted(trees, key=lambda p: p["path"])
    ]
    names = [PurePosixPath(p["path"]).name for p in parts]
    if names != [f"allocentric_RGB_videos_{i:02d}" for i in range(len(parts))]:
        raise ValueError("noncontiguous archive parts")
    labels = get_json(prefix + "CORE4D_Real/action_labels.json")
    # Explicit label-stratified development selection, never called a holdout.
    sequences = [
        next(k for k in sorted(labels) if labels[k] == action)
        for action in ("pass1_obs0", "pass2_obs0")
    ]
    evaluator = args.output / "evaluator"
    evaluator.mkdir(exist_ok=args.resume_incomplete)
    retain_text(
        evaluator / "action_labels.json", json.dumps(labels, sort_keys=True, indent=2) + "\n"
    )
    retain_text(
        args.output / "selection.json",
        json.dumps(
            {
                "sequences": sequences,
                "rule": (
                    "lexicographically first pass1_obs0 and pass2_obs0, first camera; "
                    "development selection uses author sequence labels"
                ),
                "holdout": False,
                "frame_event_labels": False,
            },
            indent=2,
        )
        + "\n",
    )
    reader = ConcatRangeReader(parts, args.cache)
    receipts = []
    with zipfile.ZipFile(reader) as archive:
        retain_text(
            args.output / "archive_members.json",
            json.dumps(
                [
                    {
                        "name": p.filename,
                        "bytes": p.file_size,
                        "compressed": p.compress_size,
                        "crc32": p.CRC,
                    }
                    for p in archive.infolist()
                ],
                indent=2,
            )
            + "\n",
        )
        for sequence in sequences:
            videos = sorted(
                n
                for n in archive.namelist()
                if f"/{sequence}/" in "/" + n and n.endswith("/color.mp4")
            )
            if not videos:
                raise ValueError(f"no raw video for {sequence}")
            video = videos[0]
            folder = video.rsplit("/", 1)[0]
            members = [
                n
                for n in archive.namelist()
                if n.startswith(folder + "/")
                and n.rsplit("/", 1)[-1]
                in {"color.mp4", "timestamp.txt", "config.json", "intrinsic.json"}
            ]
            for member in sorted(members):
                info = archive.getinfo(member)
                if not 0 < info.file_size <= 64 * 1024 * 1024:
                    raise ValueError("member exceeds bounded subset")
                data = archive.read(info)
                relative = PurePosixPath(member)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe archive member")
                path = args.output / "raw" / member
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.read_bytes() != data:
                    raise ValueError("existing extracted member differs from archive")
                path.write_bytes(data)
                receipts.append(
                    dict(
                        sequence=sequence,
                        member=member,
                        bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        zip_crc32=info.CRC,
                    )
                )
                print("extracted", member, len(data), flush=True)
    summary = dict(
        repository=REPOSITORY,
        revision=REVISION,
        transport=args.endpoint,
        parts=parts,
        receipts=receipts,
        new_range_bytes=reader.downloaded,
        full_archive_sha_verified=False,
        semantic_transitions=0,
        scope="raw public two-person development subset with separate sequence-level supervision",
    )
    (args.output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
