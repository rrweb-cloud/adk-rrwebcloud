from __future__ import annotations

from typing import Any
from typing import Optional

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types
from typing_extensions import override

from .computer import RrwebCloudPlaywrightComputer
from .config import RrwebCloudReplayConfig
from .context import CURRENT_INVOCATION_REPLAY_STATE
from .types import InvocationReplayState
from .types import ReplaySessionInfo

SESSION_STATE_KEY = "rrwebcloud_replay"


class RrwebCloudReplayPlugin(BasePlugin):
  def __init__(
      self,
      *,
      config: Optional[RrwebCloudReplayConfig] = None,
      name: str = "rrwebcloud_replay",
  ) -> None:
    super().__init__(name=name)
    self._config = config or RrwebCloudReplayConfig.from_env()
    self._wrapped_computers: list[RrwebCloudPlaywrightComputer] = []

  @property
  def config(self) -> RrwebCloudReplayConfig:
    return self._config

  def wrap_computer(self, computer: Any) -> RrwebCloudPlaywrightComputer:
    wrapped = RrwebCloudPlaywrightComputer(computer, config=self._config)
    self._wrapped_computers.append(wrapped)
    return wrapped

  @override
  async def before_run_callback(
      self, *, invocation_context: Any
  ) -> Optional[types.Content]:
    replay_state = InvocationReplayState(
        app_name=invocation_context.app_name,
        user_id=invocation_context.user_id,
        session_id=invocation_context.session.id,
        invocation_id=invocation_context.invocation_id,
    )
    CURRENT_INVOCATION_REPLAY_STATE.set(replay_state)
    return None

  @override
  async def after_run_callback(self, *, invocation_context: Any) -> None:
    replay_state = CURRENT_INVOCATION_REPLAY_STATE.get()
    if replay_state is None:
      return

    try:
      active_recording = replay_state.active_recording
      if active_recording is not None:
        await active_recording.finalize()
        replay_state.recordings.append(
            ReplaySessionInfo(
                recording_id=active_recording.recording_id,
                preview_url=active_recording.preview_url,
                session_id=replay_state.session_id,
                invocation_id=replay_state.invocation_id,
                created_at=active_recording.created_at,
                app_name=replay_state.app_name,
                user_id=replay_state.user_id,
                trace_id=replay_state.trace_id,
                metadata=dict(active_recording.metadata),
            )
        )
        replay_state.active_recording = None

      if not self._config.persist_to_session or not replay_state.recordings:
        return

      next_state = _merge_recordings(
          invocation_context.session.state.get(SESSION_STATE_KEY),
          replay_state.recordings,
      )
      state_event = Event(
          invocation_id=invocation_context.invocation_id,
          author=invocation_context.agent.name,
          actions=EventActions(state_delta={SESSION_STATE_KEY: next_state}),
      )
      await invocation_context.session_service.append_event(
          session=invocation_context.session,
          event=state_event,
      )
    finally:
      CURRENT_INVOCATION_REPLAY_STATE.set(None)

  @override
  async def close(self) -> None:
    CURRENT_INVOCATION_REPLAY_STATE.set(None)
    for wrapped_computer in self._wrapped_computers:
      await wrapped_computer.aclose()


def latest_replay_for_session_state(
    state: dict[str, Any] | None,
) -> dict[str, Any] | None:
  if not state:
    return None
  replay_state = state.get(SESSION_STATE_KEY)
  if not isinstance(replay_state, dict):
    return None
  latest = replay_state.get("latest")
  return latest if isinstance(latest, dict) else None


def _merge_recordings(
    existing_state: Any,
    recordings: list[ReplaySessionInfo],
) -> dict[str, Any]:
  state = existing_state if isinstance(existing_state, dict) else {}
  history = state.get("history")
  merged_history = list(history) if isinstance(history, list) else []
  merged_history.extend(
      [recording.model_dump(mode="json") for recording in recordings]
  )
  latest = merged_history[-1] if merged_history else None
  return {
      "latest": latest,
      "history": merged_history,
  }
