"""Tiny pytest compatibility surface for a dependency-blocked audit.

This is not pytest.  It only supports the exact decorators and assertions used
by the six frozen B6 delivery test modules so the functions can be exercised
directly when the real pytest package is unavailable.
"""

from __future__ import annotations

import math
import re
from types import SimpleNamespace


def _close(actual, expected, rel, abs_):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and set(actual) == set(expected) and all(
            _close(actual[key], value, rel, abs_) for key, value in expected.items()
        )
    if isinstance(expected, (tuple, list)):
        return isinstance(actual, (tuple, list)) and len(actual) == len(expected) and all(
            _close(a, e, rel, abs_) for a, e in zip(actual, expected, strict=True)
        )
    try:
        return math.isclose(float(actual), float(expected), rel_tol=rel, abs_tol=abs_)
    except (TypeError, ValueError):
        return actual == expected


class _Approx:
    def __init__(self, expected, *, rel=1e-6, abs=1e-12):
        self.expected = expected
        self.rel = rel
        self.abs = abs

    def __eq__(self, actual):
        return _close(actual, self.expected, self.rel, self.abs)

    def __repr__(self):
        return f"approx({self.expected!r})"


def approx(expected, *, rel=1e-6, abs=1e-12):
    return _Approx(expected, rel=rel, abs=abs)


class _Raises:
    def __init__(self, expected, match=None):
        self.expected = expected
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is None:
            raise AssertionError(f"did not raise {self.expected}")
        if not issubclass(exception_type, self.expected):
            return False
        self.value = exception
        if self.match is not None and re.search(self.match, str(exception)) is None:
            raise AssertionError(
                f"exception {exception!r} does not match pattern {self.match!r}"
            )
        return True


def raises(expected, *, match=None):
    return _Raises(expected, match=match)


def _parametrize(argnames, argvalues):
    names = tuple(argnames) if not isinstance(argnames, str) else tuple(
        item.strip() for item in argnames.split(",")
    )

    def decorate(function):
        marks = list(getattr(function, "__b6_parametrize__", ()))
        marks.append((names, tuple(argvalues)))
        function.__b6_parametrize__ = tuple(marks)
        return function

    return decorate


mark = SimpleNamespace(parametrize=_parametrize)


def fixture(function=None, **options):
    del options

    def decorate(target):
        target.__b6_fixture__ = True
        return target

    return decorate(function) if function is not None else decorate

