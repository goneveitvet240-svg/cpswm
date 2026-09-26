"""Reconstruct source-bound HFD original RGB frames and isolated author supervision."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from cpswm.data_preflight.hfd_observation_alignment import align_hfd_training

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "metadata", "intake", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--imported-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--sampling", choices=("sparse", "continuous"), default="sparse")
    args = parser.parse_args()
    result = align_hfd_training(**vars(args))
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
