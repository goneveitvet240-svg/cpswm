"""Prepare or source-rebuild the fixed VISOR author-contact development pilot."""

import argparse
import json
from pathlib import Path

from cpswm.data_preflight.visor_contact_supervision import prepare_contact_package

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = prepare_contact_package(args.source, args.output, verify=args.verify)
    print(json.dumps(result["report"], indent=2))
