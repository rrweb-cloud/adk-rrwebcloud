from __future__ import annotations

from typing import Any
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ReplaySessionInfo(BaseModel):
  model_config = ConfigDict(extra="forbid")

  recording_id: str
  preview_url: str
  session_id: str
  invocation_id: str
  created_at: float
  app_name: str
  user_id: str
  trace_id: Optional[str] = None
  metadata: dict[str, Any] = Field(default_factory=dict)


class InvocationReplayState(BaseModel):
  model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

  app_name: str
  user_id: str
  session_id: str
  invocation_id: str
  trace_id: Optional[str] = None
  recordings: list[ReplaySessionInfo] = Field(default_factory=list)
  active_recording: Any | None = None
