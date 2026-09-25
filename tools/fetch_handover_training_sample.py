"""Bounded four-worker download of the author's two training trials (CC BY 4.0).

Exact ranges and final published MD5 are checked. Existing failed ranges can be
retried; no validation/test data is downloaded. Metadata URL is recorded.
"""

import argparse
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://zenodo.org/records/10708763/files/sample_training_set.tar.gz?download=1"
SIZE = 59949643
MD5 = "c6466839bc34310fcf8e5e828874dbc7"
BLOCK = 1024 * 1024


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    cache = output / "handover-ranges"
    cache.mkdir(exist_ok=True)

    def get(pair):
        start, stop = pair
        path = cache / f"{start}-{stop}.bin"
        if path.exists() and path.stat().st_size == stop - start:
            return path
        last_error = None
        for _ in range(3):
            try:
                req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{stop - 1}"})
                with urllib.request.urlopen(req, timeout=35) as response:
                    if (
                        response.status != 206
                        or response.headers["Content-Range"] != f"bytes {start}-{stop - 1}/{SIZE}"
                    ):
                        raise ValueError("server did not honor exact range")
                    data = response.read(stop - start + 1)
                if len(data) != stop - start:
                    raise ValueError("short or oversized range")
                path.write_bytes(data)
                print(start, stop, flush=True)
                return path
            except (OSError, ValueError) as error:
                last_error = error
        raise RuntimeError(f"range failed: {start}-{stop}: {last_error}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(get, [(i, min(i + BLOCK, SIZE)) for i in range(0, SIZE, BLOCK)]))
    payload = b"".join(p.read_bytes() for p in paths)
    if len(payload) != SIZE or hashlib.md5(payload).hexdigest() != MD5:
        raise ValueError("full author archive checksum mismatch; no accepted artifact written")
    target = output / "sample_training_set.verified.tar.gz"
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("refusing to overwrite a different accepted artifact")
    target.write_bytes(payload)
    receipt = {
        "url": URL,
        "record": "https://zenodo.org/records/10708763",
        "author_md5_verified": MD5,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "license": "CC BY 4.0",
        "selection": "author provided sample of two training trials",
    }
    (output / "handover-download-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
