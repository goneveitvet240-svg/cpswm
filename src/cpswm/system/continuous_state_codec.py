"""Local JSON checkpoints for the configured CPSWM object graph.

No pickle, dynamic imports, executable payloads or model weights. The caller
provides a trusted type registry from its installed runtime. Graph references
preserve the single ledger, component aliases and method-owner cycles. This is
local recovery, not independent custody or proof of empirical calibration.
"""

from __future__ import annotations

import base64
import json
import math
import sys
import types
from datetime import datetime
from enum import Enum
from threading import RLock
from uuid import UUID

import numpy as np

LOCK_TYPE = type(RLock())
METHODS = {"_require_core_public_mutation_permission", "_runtime_operator_instances_for_execution"}


def runtime_types() -> dict[str, type]:
    """Only already-loaded CPSWM classes; a checkpoint cannot request imports."""
    result = {}
    for name, module in tuple(sys.modules.items()):
        if name.startswith("cpswm.") and module is not None:
            for value in vars(module).values():
                if isinstance(value, type) and value.__module__.startswith("cpswm."):
                    result[value.__module__ + "." + value.__qualname__] = value
    return result


class StateCodec:
    def __init__(self, registry: dict[str, type] | None = None):
        self.registry = runtime_types() if registry is None else dict(registry)

    def dumps(self, root: object) -> str:
        nodes = []
        seen = {}

        def encode(value):
            if value is None or type(value) in (bool, str, int):
                return {"value": value}
            if type(value) is float:
                if math.isnan(value):
                    raise ValueError("NaN checkpoint scalar")
                return (
                    {"value": value}
                    if math.isfinite(value)
                    else {"infinity": 1 if value > 0 else -1}
                )
            if id(value) in seen:
                return {"ref": seen[id(value)]}
            index = len(nodes)
            seen[id(value)] = index
            nodes.append(None)
            cls = type(value)
            if isinstance(value, Enum):
                node = {
                    "kind": "enum",
                    "class": cls.__module__ + "." + cls.__qualname__,
                    "name": value.name,
                }
            elif isinstance(value, UUID):
                node = {"kind": "uuid", "value": str(value)}
            elif isinstance(value, datetime):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError("naive checkpoint time")
                node = {"kind": "time", "value": value.isoformat()}
            elif type(value) is bytes:
                node = {"kind": "bytes", "value": base64.b64encode(value).decode()}
            elif cls is LOCK_TYPE:
                node = {"kind": "lock"}
            elif isinstance(value, np.ndarray):
                if value.dtype.hasobject or value.dtype.kind not in "biuf":
                    raise ValueError("unsupported checkpoint array")
                node = {
                    "kind": "array",
                    "dtype": value.dtype.str,
                    "shape": value.shape,
                    "value": base64.b64encode(value.tobytes()).decode(),
                }
            elif isinstance(value, types.MethodType):
                if value.__func__.__name__ not in METHODS:
                    raise ValueError("unregistered checkpoint callback")
                node = {
                    "kind": "method",
                    "owner": encode(value.__self__),
                    "name": value.__func__.__name__,
                }
            elif cls in (dict, list, tuple, set, frozenset):
                node = {
                    "kind": cls.__name__,
                    "items": [[encode(k), encode(v)] for k, v in value.items()]
                    if cls is dict
                    else [encode(v) for v in value],
                }
            else:
                key = cls.__module__ + "." + cls.__qualname__
                if self.registry.get(key) is not cls:
                    raise ValueError("unregistered state type: " + key)
                attrs = dict(vars(value)) if hasattr(value, "__dict__") else {}
                for parent in cls.__mro__:
                    slots = getattr(parent, "__slots__", ())
                    if isinstance(slots, str):
                        slots = (slots,)
                    for name in slots:
                        if name not in ("__dict__", "__weakref__") and hasattr(value, name):
                            attrs[name] = getattr(value, name)
                node = {
                    "kind": "object",
                    "class": key,
                    "attrs": {k: encode(v) for k, v in attrs.items()},
                }
            nodes[index] = node
            return {"ref": index}

        ref = encode(root)
        return json.dumps(
            {"schema": 1, "root": ref, "nodes": nodes}, allow_nan=False, separators=(",", ":")
        )

    def loads(self, data: str) -> object:
        if len(data) > 256 * 1024 * 1024:
            raise ValueError("checkpoint too large")
        doc = json.loads(data)
        if doc.get("schema") != 1:
            raise ValueError("unsupported checkpoint schema")
        nodes = doc["nodes"]
        cache = {}
        active = set()
        if len(nodes) > 1000000:
            raise ValueError("checkpoint graph too large")

        def decode(ref):
            if (
                set(ref) == {"infinity"}
                and type(ref["infinity"]) is int
                and ref["infinity"] in (-1, 1)
            ):
                return math.inf * ref["infinity"]
            if set(ref) == {"value"}:
                value = ref["value"]
                if value is not None and type(value) not in (str, bool, int, float):
                    raise ValueError("invalid scalar")
                if type(value) is float and not math.isfinite(value):
                    raise ValueError("invalid scalar")
                return value
            if (
                set(ref) != {"ref"}
                or type(ref["ref"]) is not int
                or not 0 <= ref["ref"] < len(nodes)
            ):
                raise ValueError("invalid graph reference")
            i = ref["ref"]
            if i in cache:
                return cache[i]
            if i in active:
                raise ValueError("unsupported immutable cycle")
            active.add(i)
            node = nodes[i]
            kind = node["kind"]
            if kind == "object":
                cls = self.registry.get(node["class"])
                if cls is None or issubclass(cls, Enum):
                    raise ValueError("unregistered checkpoint class")
                result = object.__new__(cls)
                cache[i] = result
                for name, value in node["attrs"].items():
                    if name in ("__class__", "__dict__", "__weakref__"):
                        raise ValueError("invalid checkpoint attribute")
                    object.__setattr__(result, name, decode(value))
            elif kind == "enum":
                cls = self.registry.get(node["class"])
                if cls is None or not issubclass(cls, Enum):
                    raise ValueError("unregistered enum")
                result = cls[node["name"]]
            elif kind == "uuid":
                result = UUID(node["value"])
            elif kind == "time":
                result = datetime.fromisoformat(node["value"])
                if result.tzinfo is None or result.utcoffset() is None:
                    raise ValueError("naive time")
            elif kind == "bytes":
                result = base64.b64decode(node["value"], validate=True)
            elif kind == "lock":
                result = RLock()
            elif kind == "array":
                dtype = np.dtype(node["dtype"])
                shape = node["shape"]
                wire = base64.b64decode(node["value"], validate=True)
                if (
                    dtype.hasobject
                    or dtype.kind not in "biuf"
                    or any(type(n) is not int or n < 0 for n in shape)
                    or math.prod(shape) * dtype.itemsize != len(wire)
                ):
                    raise ValueError("invalid array")
                result = np.frombuffer(wire, dtype=dtype).reshape(shape).copy()
            elif kind == "method":
                if node["name"] not in METHODS:
                    raise ValueError("unregistered method")
                result = getattr(decode(node["owner"]), node["name"])
            elif kind == "dict":
                result = {}
                cache[i] = result
                for k, v in node["items"]:
                    key = decode(k)
                    if key in result:
                        raise ValueError("duplicate checkpoint mapping key")
                    result[key] = decode(v)
            elif kind == "list":
                result = []
                cache[i] = result
                result.extend(decode(v) for v in node["items"])
            elif kind in ("tuple", "set", "frozenset"):
                result = {"tuple": tuple, "set": set, "frozenset": frozenset}[kind](
                    decode(v) for v in node["items"]
                )
            else:
                raise ValueError("unsupported checkpoint node")
            cache[i] = result
            active.remove(i)
            return result

        return decode(doc["root"])
