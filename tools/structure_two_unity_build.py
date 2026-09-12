"""Bounded real Unity source build. No license activation or installer bypass."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    editor = args.editor.resolve(strict=True)
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if args.timeout <= 0 or args.timeout > 14400:
        raise ValueError("build timeout must be 1..14400 seconds")
    if output == source or source in output.parents:
        raise ValueError("build output must be outside the source checkout")
    version_path = source / "unity/ProjectSettings/ProjectVersion.txt"
    if "m_EditorVersion: 2020.3.25f1\n" not in version_path.read_text():
        raise ValueError("source editor version differs from frozen contract")
    entry = source / "unity/Assets/Editor/CpswmBuild.cs"
    template = Path(__file__).parent / "unity/CpswmBuild.cs"
    if digest(entry) != digest(template):
        raise ValueError("actual build entry does not match reviewed template")
    for scene in ("FloorPlan1_physics.unity", "Procedural/Procedural.unity"):
        if not (source / "unity/Assets/Scenes" / scene).is_file():
            raise ValueError("full real scene source has not been checked out")
    output.mkdir(parents=True, exist_ok=False)
    paths = [
        version_path,
        entry,
        source / "unity/Packages/manifest.json",
        source / "unity/Packages/packages-lock.json",
        source / "unity/Assets/Scripts/AgentManager.cs",
        source / "unity/Assets/Scripts/BaseFPSAgentController.cs",
    ]
    before = {str(p.relative_to(source)): digest(p) for p in paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    log = output / "editor.private.log"
    receipt = output / "unity-result.json"
    application = output / "cpswm-development.app"
    command = [
        str(editor),
        "-batchmode",
        "-quit",
        "-logFile",
        str(log),
        "-projectPath",
        str(source / "unity"),
        "-buildTarget",
        "OSXUniversal",
        "-executeMethod",
        "CpswmBuild.MacDevelopment",
    ]
    evidence = {
        "schema": "cpswm-unity-build-runner@1",
        "command": command,
        "head": head,
        "source_before": before,
        "python": sys.version,
        "editor_sha256": digest(editor),
        "build_verified": False,
        "human_execution_verified": False,
        "training_started": False,
        "raw_log_is_private": True,
    }
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=source,
            timeout=args.timeout,
            env={
                **os.environ,
                "CPSWM_UNITY_OUTPUT": str(application),
                "CPSWM_UNITY_RECEIPT": str(receipt),
                "CPSWM_UNITY_SOURCE_REVISION": head,
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        (output / "console.private.log").write_text(result.stdout)
        evidence["exit_code"] = result.returncode
        if result.returncode != 0 or not receipt.is_file():
            raise RuntimeError(
                "Unity did not produce a successful build receipt; inspect private log"
            )
        actual = json.loads(receipt.read_text())
        if (
            actual.get("result") != "Succeeded"
            or actual.get("errors") != 0
            or actual.get("editorVersion") != "2020.3.25f1"
            or actual.get("sourceRevision") != head
        ):
            raise RuntimeError("actual build receipt failed or mismatched")
        dll = application / "Contents/Resources/Data/Managed/AI2-THOR-Base.dll"
        executables = list((application / "Contents/MacOS").iterdir())
        if not dll.is_file() or not any(p.is_file() and os.access(p, os.X_OK) for p in executables):
            raise RuntimeError("actual gameplay assembly or executable is missing")
        evidence["gameplay_sha256"] = digest(dll)
        evidence["build_verified"] = True
    except Exception as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        evidence["seconds"] = time.monotonic() - started
        after = {str(p.relative_to(source)): digest(p) for p in paths}
        evidence["source_after"] = after
        evidence["source_unchanged"] = before == after
        evidence["build_verified"] &= before == after
        if log.is_file():
            evidence["private_log_sha256"] = digest(log)
        (output / "runner-result.json").write_text(json.dumps(evidence, indent=2))
    print(
        json.dumps(
            {
                key: evidence.get(key)
                for key in ("build_verified", "source_unchanged", "error", "seconds")
            }
        )
    )
    return int(not evidence["build_verified"])


if __name__ == "__main__":
    raise SystemExit(main())
