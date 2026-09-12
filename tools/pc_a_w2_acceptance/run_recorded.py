"""Run one local review command; exclusive logs, explicit cwd/environment, no gate."""

import argparse
import datetime
import json
import os
import subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--name", required=True)
p.add_argument("--cwd", type=Path, required=True)
p.add_argument("--env", action="append", default=[])
p.add_argument("command", nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command[:1] == ["--"] else a.command
if not command or Path(a.name).name != a.name:
    p.error("command and simple record name required")
a.output.mkdir(parents=True, exist_ok=True)
changes = dict(item.split("=", 1) for item in a.env)
record = {
    "command": command,
    "cwd": str(a.cwd.resolve()),
    "environment_overrides": changes,
    "started_utc": datetime.datetime.now(datetime.UTC).isoformat(),
}
with (a.output / (a.name + ".command.json")).open("x") as meta:
    json.dump(record, meta, indent=2)
with (
    (a.output / (a.name + ".stdout.log")).open("x") as out,
    (a.output / (a.name + ".stderr.log")).open("x") as err,
):
    result = subprocess.run(
        command, cwd=a.cwd, env={**os.environ, **changes}, stdout=out, stderr=err
    )
record.update(
    exit_code=result.returncode, ended_utc=datetime.datetime.now(datetime.UTC).isoformat()
)
(a.output / (a.name + ".command.json")).write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"name": a.name, "exit_code": result.returncode}))
raise SystemExit(result.returncode)
