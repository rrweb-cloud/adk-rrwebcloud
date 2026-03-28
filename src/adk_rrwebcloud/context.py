from __future__ import annotations

from contextvars import ContextVar

from .types import InvocationReplayState

CURRENT_INVOCATION_REPLAY_STATE: ContextVar[InvocationReplayState | None] = (
    ContextVar("rrwebcloud_current_invocation_state", default=None)
)
