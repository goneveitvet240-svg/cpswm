"""Deterministic read-race counterexample using real cached module execution."""

import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

source_root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
revision = sys.argv[3]
root = Path(tempfile.mkdtemp(prefix="cpswm-r6-readrace-", dir="/private/tmp"))
shutil.copytree(source_root / ".venv", root / ".venv", symlinks=True)
for directory in ("src/cpswm", "tools", "tests"):
    (root / directory).mkdir(parents=True)
for name in ("structure_two_unified_acceptance.py", "structure_two_pytest_runtime.py"):
    (root / "tools" / name).write_bytes(
        subprocess.check_output(
            ["git", "-C", str(source_root), "show", revision + ":tools/" + name]
        )
        if revision != "working"
        else (source_root / "tools" / name).read_bytes()
    )
(root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["src"]\n')
(root / ".gitignore").write_text(".venv/\n__pycache__/\n.pytest_cache/\n")
(root / "src/cpswm/__init__.py").write_text("VALUE = 7\n")
victim = root / "src/cpswm/read_race.py"
victim.write_text("VALUE = 9\n")
stamp = victim.stat().st_mtime_ns
py_compile.compile(
    str(victim), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
)
victim.write_text("VALUE = 1\n")
os.utime(victim, ns=(stamp, stamp))
(root / "tests/test_read_race.py").write_text(
    "def test_live():\n from cpswm import read_race\n assert read_race.VALUE == 9\n"
)
(root / "tests/conftest.py").write_text("""from pathlib import Path
original_read = Path.read_bytes
reads = 0
def racing_read(self):
 global reads
 if self.name == 'read_race.py':
  reads += 1
  if reads == 2:
   return b'VALUE = 9\\n'
 return original_read(self)
Path.read_bytes = racing_read
""")
for args in (
    ("init", "-q"),
    ("add", "."),
    (
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Read race fixture",
    ),
):
    subprocess.run(["git", "-C", str(root), *args], check=True)
spec = importlib.util.spec_from_file_location(
    "coordinator", root / "tools/structure_two_unified_acceptance.py"
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
journal = m.Journal(root / m.RUN_AREA / "read_race")
frozen = m.source_snapshot(root)
error = None
try:
    m.run_stages(
        root,
        journal,
        [m.matrix_stage(root, journal, "matrix", ("tests/test_read_race.py",))],
        frozen,
        (),
        environment=m.execution_environment(root),
    )
except ValueError as exc:
    error = str(exc)
shutil.copytree(journal.path, out / ("read_race_" + revision))
print(
    json.dumps(
        {
            "revision": revision,
            "root": str(root),
            "status": journal.value["status"],
            "error": error,
            "source_unchanged": m.source_snapshot(root) == frozen,
        }
    )
)
assert (error is not None) == (revision == "working")
