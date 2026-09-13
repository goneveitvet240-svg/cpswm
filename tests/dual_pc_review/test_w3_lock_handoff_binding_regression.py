from __future__ import annotations

from collections.abc import Callable

import pytest
from test_structure_two_production_system import _system_and_transition

import cpswm.system.prototype_spine as prototype_spine
from cpswm.system.structure_two_particle_workspace import NativeParticleWorkspace


@pytest.mark.parametrize("method_name", prototype_spine._PARTICLE_WORKSPACE_BOUND_METHOD_NAMES)
def test_hot_workspace_guard_rejects_every_class_callable_replacement(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    """Amortization must not turn private validator replacement into a blind spot."""

    system, _ = _system_and_transition()

    def replacement(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(NativeParticleWorkspace, method_name, replacement)
    with pytest.raises(ValueError, match=r"callable binding was replaced"):
        system.core._check_particle_workspace_binding()


def test_hot_workspace_guard_does_not_repeat_full_source_compilation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The transaction hot path uses anchors, while all live checks still run."""

    system, _ = _system_and_transition()
    original: Callable[..., object] = prototype_spine.bind_runtime_callable

    def unexpected_rebind(**_kwargs: object) -> object:
        raise AssertionError("hot guard repeated full source compilation")

    monkeypatch.setattr(prototype_spine, "bind_runtime_callable", unexpected_rebind)
    system.core._check_particle_workspace_binding()
    monkeypatch.setattr(prototype_spine, "bind_runtime_callable", original)

    # The cheap path is still a real integrity check, not a skipped validation.
    system.core.locations = system.core.locations[::-1]
    with pytest.raises(ValueError, match=r"world location support was rebound"):
        system.core._check_particle_workspace_binding()


def test_hot_workspace_guard_rejects_in_place_code_object_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keeping the original function object cannot conceal changed bytecode."""

    system, _ = _system_and_transition()
    target = NativeParticleWorkspace.state_payload

    def replacement(_self: NativeParticleWorkspace) -> dict[str, object]:
        return {}

    monkeypatch.setattr(target, "__code__", replacement.__code__)
    with pytest.raises(ValueError, match=r"loaded callable code changed"):
        system.core._check_particle_workspace_binding()
