"""Warm compilation cannot authorize stale disk bytes or a replaced live callable."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from uuid import UUID

import pytest

from cpswm.system.structure_two_execution import (
    _code_object_sha256,
    _source_code_objects,
    bind_runtime_callable,
)

SOURCE = (
    "from __future__ import annotations\n"
    "class Operator:\n    def invoke(self):\n        return 'good'\n"
)


def operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "cached_operator.py"
    path.write_text(SOURCE)
    spec = importlib.util.spec_from_file_location("cached_operator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "cached_operator", module)
    spec.loader.exec_module(module)
    return path, module.Operator()


def bind(instance):
    return bind_runtime_callable(
        runtime_execution_id=UUID("00000000-0000-4000-8000-000000000991"),
        operator="opceu",
        binding_slot=0,
        binding_kind="direct_operator_callable",
        instance=instance,
        callable_name="invoke",
        require_declared_member=True,
    )


def test_warm_binding_rechecks_same_size_same_mtime_disk_replacement(tmp_path, monkeypatch):
    path, instance = operator(tmp_path, monkeypatch)
    _source_code_objects.cache_clear()
    accepted = bind(instance)
    assert bind(instance) == accepted
    assert _source_code_objects.cache_info().hits >= 1
    stat = path.stat()
    replacement = SOURCE.replace("'good'", "'evil'")
    assert len(replacement) == len(SOURCE)
    path.write_text(replacement)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ValueError, match="does not match the current source"):
        bind(instance)
    path.write_text(SOURCE)
    assert bind(instance) == accepted


def test_warm_binding_rechecks_replaced_live_code_then_accepts_restored_code(tmp_path, monkeypatch):
    _, instance = operator(tmp_path, monkeypatch)
    accepted = bind(instance)
    method = type(instance).invoke
    original = method.__code__
    method.__code__ = original.replace(
        co_consts=tuple("evil" if value == "good" else value for value in original.co_consts)
    )
    try:
        assert instance.invoke() == "evil"
        with pytest.raises(ValueError, match="does not match the current source"):
            bind(instance)
    finally:
        method.__code__ = original
    assert bind(instance) == accepted


def test_warm_binding_cannot_authorize_a_deleted_source(tmp_path, monkeypatch):
    path, instance = operator(tmp_path, monkeypatch)
    bind(instance)
    path.unlink()
    with pytest.raises(ValueError, match="source is unavailable"):
        bind(instance)


def test_compilation_cache_preserves_path_and_all_code_digests_and_is_bounded(tmp_path):
    _source_code_objects.cache_clear()
    for index in range(40):
        path = tmp_path / f"operator_{index}.py"
        fresh = _source_code_objects.__wrapped__(path, SOURCE.encode())
        cold = _source_code_objects(path, SOURCE.encode())
        warm = _source_code_objects(path, SOURCE.encode())
        assert warm is cold
        assert [_code_object_sha256(c) for c in warm] == [_code_object_sha256(c) for c in fresh]
        assert all(c.co_filename == str(path) for c in warm)
    assert _source_code_objects.cache_info().currsize == 32
    assert _source_code_objects.cache_info().hits == 40
