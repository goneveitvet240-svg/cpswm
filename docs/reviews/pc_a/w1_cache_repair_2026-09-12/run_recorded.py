import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

out = Path(sys.argv[1])
label = sys.argv[2]
cwd = Path(sys.argv[3])
argv = sys.argv[4:]
out.mkdir(parents=True, exist_ok=True)
start = datetime.datetime.now(datetime.UTC).isoformat()
t = time.monotonic()
with (
    (out / (label + ".stdout.log")).open("xb") as stdout,
    (out / (label + ".stderr.log")).open("xb") as stderr,
):
    p = subprocess.run(argv, cwd=cwd, stdout=stdout, stderr=stderr)
value = {
    "argv": argv,
    "cwd": str(cwd),
    "start": start,
    "end": datetime.datetime.now(datetime.UTC).isoformat(),
    "seconds": time.monotonic() - t,
    "exit_code": p.returncode,
    "environment": {
        k: v
        for k, v in os.environ.items()
        if k.startswith(("S2_", "PYTEST", "PYTHON", "VIRTUAL_ENV"))
    },
}
(out / (label + ".command.json")).write_text(json.dumps(value, indent=2) + "\n")
print(json.dumps(value))
sys.exit(p.returncode)
