import datetime
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

root = pathlib.Path.cwd()
logs = root / "benchmarks/structure_two/evidence_repair_supplement_2026_09_11/validation_logs"
name = sys.argv[1]
argv = sys.argv[2:]
start = datetime.datetime.now(datetime.UTC).isoformat()
begin = time.monotonic()
record = {
    "name": name,
    "argv": argv,
    "cwd": str(root),
    "start": start,
    "python": sys.version,
    "environment": {
        k: os.environ.get(k)
        for k in [
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTEST_PLUGINS",
            "PYTEST_ADDOPTS",
            "PYTHONPATH",
            "PYTHONHASHSEED",
        ]
    },
}
print(json.dumps(record), flush=True)
with (
    (logs / (name + ".stdout.log")).open("xb") as out,
    (logs / (name + ".stderr.log")).open("xb") as err,
):
    result = subprocess.run(argv, cwd=root, stdout=out, stderr=err)
record.update(
    exit_code=result.returncode,
    end=datetime.datetime.now(datetime.UTC).isoformat(),
    seconds=time.monotonic() - begin,
)
for stream in ["stdout", "stderr"]:
    path = logs / (name + "." + stream + ".log")
    raw = path.read_bytes()
    zipped = path.with_suffix(".log.gz")
    zipped.write_bytes(gzip.compress(raw, mtime=0))
    path.unlink()
    record[stream] = {
        "path": str(zipped.relative_to(root)),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if stream == "stdout":
        print(raw[-4000:].decode(errors="replace"), flush=True)
with (logs / "commands.jsonl").open("a") as f:
    f.write(json.dumps(record) + "\n")
print(json.dumps(record), flush=True)
sys.exit(result.returncode)
