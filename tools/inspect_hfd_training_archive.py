"""Inspect or independently reconstruct the author's full HFD training evidence."""

import argparse
import json
from pathlib import Path

import cv2

from cpswm.data_preflight.full_hfd_training import inspect_full_training

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(2)
    result = inspect_full_training(args.archive, args.metadata, args.output, verify=args.verify)
    print(
        json.dumps(
            {
                k: v
                for k, v in result["report"].items()
                if k not in {"trials", "quarantined_trials"}
            },
            indent=2,
        )
    )
    print(json.dumps({"quarantined_trials": result["report"]["quarantined_trials"]}, indent=2))
