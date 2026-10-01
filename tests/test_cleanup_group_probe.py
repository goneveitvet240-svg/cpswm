"""A transient group probe error is retried, never interpreted as cleanup success."""

from __future__ import annotations

import os
import signal
import subprocess
import sys

import pytest
from test_structure_two_unified_acceptance import coordinator


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
@pytest.mark.parametrize("persistent", [False, True])
def test_group_probe_requires_a_real_disappearance_or_hard_cleanup_failure(monkeypatch, persistent):
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True
    )
    real_killpg = os.killpg
    probes = []

    def probe(group, signum):
        if group == process.pid and signum == 0:
            probes.append(signum)
            if persistent or len(probes) == 1:
                raise PermissionError("controlled Darwin group-probe race")
        if group == process.pid and persistent and signum == signal.SIGKILL:
            raise PermissionError("group remains inaccessible at cleanup deadline")
        return real_killpg(group, signum)

    try:
        with monkeypatch.context() as context:
            context.setattr(coordinator.os, "killpg", probe)
            if persistent:
                with pytest.raises(PermissionError, match="remains inaccessible"):
                    coordinator.stop_process(process)
            else:
                coordinator.stop_process(process)
        assert len(probes) >= 2
        assert process.poll() is not None
        with pytest.raises(ProcessLookupError):
            real_killpg(process.pid, 0)
    finally:
        # A failed assertion cannot leave the actual owned sleeper behind.
        coordinator.stop_process(process)
