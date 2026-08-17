"""M04 in-process commands, events, handlers, tracing, and replay."""

from .contracts import (
    HandlerExecutionRecord,
    HandlerStatus,
    MessageKind,
    RetryPolicy,
    RuntimeMessage,
    RuntimeMessageRecord,
    VersionBundle,
)
from .handlers import ExecutionContext, HandlerOutput
from .provenance import (
    RuntimeProvenanceError,
    build_replay_manifest,
    build_version_bundle,
    git_head_code_version,
    source_tree_sha256,
)
from .replay import (
    ReplayInputBindingError,
    ReplayRun,
    ReplayRunner,
    compare_replay_runs,
)
from .runtime import (
    HandlerFailedError,
    HandlerRegistrationError,
    InProcessRuntime,
    RetryableHandlerError,
    RuntimeDispatchResult,
)

__all__ = [
    "ExecutionContext",
    "HandlerExecutionRecord",
    "HandlerFailedError",
    "HandlerOutput",
    "HandlerRegistrationError",
    "HandlerStatus",
    "InProcessRuntime",
    "MessageKind",
    "ReplayInputBindingError",
    "ReplayRun",
    "ReplayRunner",
    "RetryPolicy",
    "RetryableHandlerError",
    "RuntimeDispatchResult",
    "RuntimeMessage",
    "RuntimeMessageRecord",
    "RuntimeProvenanceError",
    "VersionBundle",
    "build_replay_manifest",
    "build_version_bundle",
    "compare_replay_runs",
    "git_head_code_version",
    "source_tree_sha256",
]
