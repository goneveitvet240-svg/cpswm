"""Run unchanged PC-B tests/observations against two pinned native code trees."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
PY = Path(
    "/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/.venv/bin/python"
)
B_SHA = "9195dd4b3872cbf770bd73ad4c84cca007137c3d"
ROOTS = {
    "r6": (Path("/private/tmp/cpswm-pc-a-b-r6.96bIgR"), "1bd513f51ab7e54a7290870a5f34b524254d55c6"),
    "r7": (Path("/private/tmp/cpswm-pc-a-b-r7.QWWcBF"), "62870a3a38fce882b25d8d77f1d0526cca6fbc14"),
}
TEST = "tests/test_structure_two_w3_r6_pc_b_review.py"
OBS = "docs/reviews/data/pc_b_w3_r6_independent_20260912/w3_five_case_observations.py"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def sources(root):
    names = (
        git(root, "ls-files", "-z", "src", "tests", "tools", "apps", "configs").decode().split("\0")
    )
    return {name: sha((root / name).read_bytes()) for name in names if name}


label = sys.argv[1]
root, commit = ROOTS[label]
assert git(root, "rev-parse", "HEAD").decode().strip() == commit
assert not git(root, "diff", "--name-only")
overlay = {}
for name in (TEST, OBS):
    raw = git(REPO, "show", B_SHA + ":" + name)
    assert (root / name).read_bytes() == raw
    overlay[name] = sha(raw)
before = sources(root)
env = os.environ.copy()
for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONOPTIMIZE"):
    env.pop(key, None)
env.update(
    PYTHONPATH=str(root / "src") + os.pathsep + str(root / "tests"),
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    OPENBLAS_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
)
identity_code = (
    "import sys,json,importlib.metadata as m; "
    "import test_structure_two_formal_revision_lineage; "
    "import cpswm.system.prototype_spine as s; "
    "print(json.dumps(dict(executable=sys.executable,version=sys.version,prefix=sys.prefix,"
    'loaded_spine=s.__file__,packages=sorted((d.metadata["Name"],d.version) '
    "for d in m.distributions()))))"
)
identity = json.loads(subprocess.check_output([str(PY), "-c", identity_code], cwd=root, env=env))
assert identity["loaded_spine"] == str(root / "src/cpswm/system/prototype_spine.py")
commands = []
for kind, args in (
    (
        "tests",
        [
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "-p",
            "no:cacheprovider",
            "--junitxml=" + str(OUT / (label + ".xml")),
            TEST,
        ],
    ),
    ("observations", [OBS]),
):
    argv = [str(PY), *args]
    start = time.time()
    with (
        (OUT / (label + "_" + kind + ".stdout.log")).open("x") as stdout,
        (OUT / (label + "_" + kind + ".stderr.log")).open("x") as stderr,
    ):
        result = subprocess.run(argv, cwd=root, env=env, stdout=stdout, stderr=stderr)
    commands.append(
        dict(
            kind=kind,
            argv=argv,
            cwd=str(root),
            start=start,
            end=time.time(),
            exit_code=result.returncode,
        )
    )
    print(label, kind, result.returncode, flush=True)
after = sources(root)
assert before == after
assert not git(root, "diff", "--name-only")
record = dict(
    tested_sha=commit,
    review_input_sha=B_SHA,
    overlay_sha256=overlay,
    source_before=before,
    source_after_equal=True,
    identity=identity,
    interpreter_binary_sha256=sha(PY.resolve().read_bytes()),
    commands=commands,
    environment={
        k: env.get(k)
        for k in (
            "PYTHONPATH",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTHONDONTWRITEBYTECODE",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        )
    },
    observation_label_notice=(
        "Unchanged B recorder embeds R6 tested_sha; use this envelope for actual target."
    ),
)
(OUT / (label + ".command.json")).write_text(json.dumps(record, indent=2) + "\n")
assert commands[1]["exit_code"] == 0
print((OUT / (label + "_tests.stdout.log")).read_text()[-1800:])
