"""Official openpi MessagePack protocol with bounded connection/response waits."""

from __future__ import annotations

from importlib import import_module
from typing import Any


class BoundedWebsocketPolicy:
    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        msgpack_numpy = import_module("openpi_client.msgpack_numpy")
        connect = import_module("websockets.sync.client").connect

        self.codec = msgpack_numpy
        self.timeout = timeout
        self.socket = connect(
            f"ws://{host}:{port}", compression=None, max_size=64 * 1024 * 1024, open_timeout=timeout
        )
        self.metadata = self.codec.unpackb(self.socket.recv(timeout=timeout))

    def infer(self, observation: dict[str, Any]) -> dict[str, Any]:
        self.socket.send(self.codec.packb(observation))
        reply = self.socket.recv(timeout=self.timeout)
        if isinstance(reply, str):
            raise RuntimeError(f"openpi server error: {reply}")
        result = self.codec.unpackb(reply)
        if not isinstance(result, dict) or not all(isinstance(k, str) for k in result):
            raise RuntimeError("openpi server returned a non-object response")
        return result

    def close(self) -> None:
        self.socket.close()
