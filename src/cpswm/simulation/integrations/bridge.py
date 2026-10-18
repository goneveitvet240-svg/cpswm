"""JSON-lines boundary to the locked Python environment of native CPSWM."""

from __future__ import annotations

import json
import selectors
import subprocess
from pathlib import Path
from typing import Any


class NativeBridge:
    def __init__(self, python: str, root: Path, episode: str, arm: str = "native_joint") -> None:
        self.process = subprocess.Popen(
            [
                python,
                str(root / "tools/simulation_memory_worker.py"),
                "--episode",
                episode,
                "--arm",
                arm,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=root,
        )
        self.timeout = 120.0
        self.episode = episode
        try:
            self.initial = self._read()
        except BaseException:
            self.close()
            raise

    def _read(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout):
                raise TimeoutError("CPSWM worker timed out")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("CPSWM worker exited without a receipt")
        reply = json.loads(line)
        if not isinstance(reply, dict) or not all(isinstance(k, str) for k in reply):
            raise RuntimeError("CPSWM worker returned a non-object receipt")
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error", "CPSWM worker error"))
        return reply

    def observe(self, event: dict[str, Any]) -> dict[str, Any]:
        if self.process.poll() is not None:
            raise RuntimeError("CPSWM worker is not running")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(event, allow_nan=False) + "\n")
        self.process.stdin.flush()
        return self._read()

    def close(self) -> None:
        if self.process.poll() is None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()
