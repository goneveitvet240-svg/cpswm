"""Run source-bound checks in a specified checkout, retaining every failed run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--native-environment", action="store_true")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def snapshot():
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("src", "tests", "configs", "artifacts", "apps", "tools")
            for p in sorted((root / folder).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        }

    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(root / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    if args.native_environment:
        for key in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE"):
            env.pop(key, None)
        probe = json.loads(
            subprocess.check_output(
                [
                    args.python,
                    "-c",
                    "import sys,json,cpswm; print(json.dumps([sys.prefix,cpswm.__file__]))",
                ],
                cwd=root,
                env=env,
                text=True,
            )
        )
        if Path(probe[0]).absolute() != root / ".venv" or not Path(
            probe[1]
        ).resolve().is_relative_to(root / "src"):
            raise ValueError("native environment must load this checkout from its own venv")
    rest = args.args[1:] if args.args[:1] == ["--"] else args.args
    command = [args.python, *rest]
    before = snapshot()
    start = time.time()
    record = {
        "root": str(root),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "command": command,
        "started_unix": start,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_before": before,
        "environment": {
            k: env.get(k)
            for k in (
                "PYTHONPATH",
                "PYTHONDONTWRITEBYTECODE",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OMP_NUM_THREADS",
                "S2_AUDIT_BUNDLE",
            )
        },
    }
    (output / "started.json").write_text(json.dumps(record, indent=2) + "\n")
    with (output / "stdout.log").open("w") as out, (output / "stderr.log").open("w") as err:
        result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=err)
    after = snapshot()
    record.update(
        exit_code=result.returncode,
        seconds=time.time() - start,
        source_after=after,
        source_unchanged=before == after,
    )
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: record[k] for k in ("head", "exit_code", "seconds", "source_unchanged")}))
    print((output / "stdout.log").read_text()[-4000:])
    raise SystemExit(result.returncode if before == after else 125)


if __name__ == "__main__":
    main()
