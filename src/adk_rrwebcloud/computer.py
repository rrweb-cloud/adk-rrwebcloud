from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Literal
from typing import Optional

from google.adk.tools.computer_use.base_computer import BaseComputer
from google.adk.tools.computer_use.base_computer import ComputerEnvironment
from google.adk.tools.computer_use.base_computer import ComputerState
from opentelemetry import trace
from typing_extensions import override

from .client import RrwebCloudApiClient
from .config import RrwebCloudReplayConfig
from .context import CURRENT_INVOCATION_REPLAY_STATE
from .types import ReplaySessionInfo

logger = logging.getLogger(__name__)

_BINDING_NAME_PREFIX = "__adk_rrwebcloud_emit_"


class _RecordingSession:
  def __init__(
      self,
      *,
      client: RrwebCloudApiClient,
      config: RrwebCloudReplayConfig,
      recording_id: str,
      metadata: dict[str, Any],
      preview_url: str,
  ) -> None:
    self._client = client
    self._config = config
    self.recording_id = recording_id
    self.metadata = metadata
    self.preview_url = preview_url
    self.created_at = time.time()
    self._events: list[dict[str, Any]] = []
    self._install_lock = asyncio.Lock()
    self._installed_page_ids: set[int] = set()

  def add_event(self, event: Any) -> None:
    if isinstance(event, dict):
      self._events.append(event)

  async def install_on(self, *, page: Any, context: Any | None) -> None:
    page_id = id(page)
    if page_id in self._installed_page_ids:
      return

    async with self._install_lock:
      if page_id in self._installed_page_ids:
        return

      binding_name = f"{_BINDING_NAME_PREFIX}{self.recording_id.replace('-', '_')}"

      async def _emit_event(_: Any, event: Any) -> None:
        self.add_event(event)

      if hasattr(page, "expose_binding"):
        await page.expose_binding(binding_name, _emit_event)

      init_script = _build_rrweb_init_script(
          binding_name=binding_name,
          rrweb_cdn_url=self._config.rrweb_cdn_url,
          block_class=self._config.block_class,
          mask_text_class=self._config.mask_text_class,
      )

      if context is not None and hasattr(context, "add_init_script"):
        await context.add_init_script(init_script)
      elif hasattr(page, "add_init_script"):
        await page.add_init_script(init_script)

      if hasattr(page, "evaluate"):
        try:
          await page.evaluate(init_script)
        except Exception:
          logger.debug("Failed to eagerly evaluate rrweb init script.")

      self._installed_page_ids.add(page_id)

  async def finalize(self) -> None:
    if not self._config.should_capture:
      return
    await self._client.ingest_events(
        recording_id=self.recording_id,
        metadata=self.metadata,
        events=self._events,
    )


def _build_rrweb_init_script(
    *,
    binding_name: str,
    rrweb_cdn_url: str,
    block_class: str,
    mask_text_class: str,
) -> str:
  return f"""
(() => {{
  const bindingName = {binding_name!r};
  const rrwebCdnUrl = {rrweb_cdn_url!r};
  const blockClass = {block_class!r};
  const maskTextClass = {mask_text_class!r};
  const install = async () => {{
    if (window.__adkRrwebCloudRecorderStarted) {{
      return;
    }}
    if (!window.rrweb || !window.rrweb.record) {{
      await new Promise((resolve, reject) => {{
        const existing = document.querySelector(
          `script[data-adk-rrwebcloud="${{rrwebCdnUrl}}"]`
        );
        if (existing) {{
          existing.addEventListener("load", () => resolve(), {{ once: true }});
          existing.addEventListener("error", () => reject(), {{ once: true }});
          return;
        }}
        const script = document.createElement("script");
        script.src = rrwebCdnUrl;
        script.async = true;
        script.dataset.adkRrwebcloud = rrwebCdnUrl;
        script.onload = () => resolve();
        script.onerror = () => reject();
        document.head.appendChild(script);
      }});
    }}
    if (!window.rrweb || !window.rrweb.record) {{
      return;
    }}
    window.__adkRrwebCloudRecorderStop = window.rrweb.record({{
      emit(event) {{
        if (typeof window[bindingName] === "function") {{
          window[bindingName](event);
        }}
      }},
      blockClass,
      maskTextClass,
      recordCanvas: false,
      collectFonts: false,
    }});
    window.__adkRrwebCloudRecorderStarted = true;
  }};
  install().catch(() => undefined);
}})();
"""


class RrwebCloudPlaywrightComputer(BaseComputer):
  def __init__(
      self,
      computer: BaseComputer,
      *,
      config: Optional[RrwebCloudReplayConfig] = None,
      client: Optional[RrwebCloudApiClient] = None,
  ) -> None:
    self._computer = computer
    self._config = config or RrwebCloudReplayConfig.from_env()
    self._client = client or RrwebCloudApiClient(self._config)

  async def _ensure_recording_started(self) -> None:
    replay_state = CURRENT_INVOCATION_REPLAY_STATE.get()
    if replay_state is None or not self._config.should_capture:
      return

    recording = replay_state.active_recording
    if recording is None:
      trace_id = replay_state.trace_id or _current_trace_id()
      recording_id = str(uuid.uuid4())
      metadata = {
          "adk_app_name": replay_state.app_name,
          "adk_user_id": replay_state.user_id,
          "adk_session_id": replay_state.session_id,
          "adk_invocation_id": replay_state.invocation_id,
      }
      if trace_id:
        metadata["trace_id"] = trace_id
      recording = _RecordingSession(
          client=self._client,
          config=self._config,
          recording_id=recording_id,
          metadata=metadata,
          preview_url=self._client.preview_url(recording_id),
      )
      replay_state.active_recording = recording

    page = self._resolve_page()
    if page is None:
      return

    await recording.install_on(page=page, context=self._resolve_context(page))

  def _should_start_recording(
      self, state: ComputerState | None, page: Any | None
  ) -> bool:
    url = state.url if state is not None else None
    if not isinstance(url, str) or not url:
      page_url = getattr(page, "url", None)
      url = page_url if isinstance(page_url, str) else None
    if not isinstance(url, str) or not url:
      return False
    return not url.startswith("about:blank")

  async def finalize_current_recording(self) -> ReplaySessionInfo | None:
    replay_state = CURRENT_INVOCATION_REPLAY_STATE.get()
    if replay_state is None:
      return None
    recording = replay_state.active_recording
    if recording is None:
      return None

    await recording.finalize()
    replay_state.active_recording = None
    replay_info = ReplaySessionInfo(
        recording_id=recording.recording_id,
        preview_url=recording.preview_url,
        session_id=replay_state.session_id,
        invocation_id=replay_state.invocation_id,
        created_at=recording.created_at,
        app_name=replay_state.app_name,
        user_id=replay_state.user_id,
        trace_id=replay_state.trace_id or _current_trace_id(),
        metadata=dict(recording.metadata),
    )
    replay_state.recordings.append(replay_info)
    return replay_info

  def _resolve_page(self) -> Any | None:
    for attr_name in ("page", "_page", "current_page"):
      if hasattr(self._computer, attr_name):
        return getattr(self._computer, attr_name)
    return None

  def _resolve_context(self, page: Any | None) -> Any | None:
    for attr_name in ("context", "_context", "browser_context"):
      if hasattr(self._computer, attr_name):
        return getattr(self._computer, attr_name)
    if page is not None and hasattr(page, "context"):
      context = getattr(page, "context")
      return context() if callable(context) else context
    return None

  async def _call_and_record(
      self,
      method: Callable[..., Awaitable[ComputerState]],
      *args: Any,
      **kwargs: Any,
  ) -> ComputerState:
    state = await method(*args, **kwargs)
    page = self._resolve_page()
    if self._should_start_recording(state, page):
      await self._ensure_recording_started()
    return state

  @override
  async def screen_size(self) -> tuple[int, int]:
    return await self._computer.screen_size()

  @override
  async def open_web_browser(self) -> ComputerState:
    return await self._call_and_record(self._computer.open_web_browser)

  @override
  async def click_at(self, x: int, y: int) -> ComputerState:
    return await self._call_and_record(self._computer.click_at, x, y)

  @override
  async def hover_at(self, x: int, y: int) -> ComputerState:
    return await self._call_and_record(self._computer.hover_at, x, y)

  @override
  async def type_text_at(
      self,
      x: int,
      y: int,
      text: str,
      press_enter: bool = True,
      clear_before_typing: bool = True,
  ) -> ComputerState:
    return await self._call_and_record(
        self._computer.type_text_at,
        x,
        y,
        text,
        press_enter=press_enter,
        clear_before_typing=clear_before_typing,
    )

  @override
  async def scroll_document(
      self, direction: Literal["up", "down", "left", "right"]
  ) -> ComputerState:
    return await self._call_and_record(self._computer.scroll_document, direction)

  @override
  async def scroll_at(
      self,
      x: int,
      y: int,
      direction: Literal["up", "down", "left", "right"],
      magnitude: int,
  ) -> ComputerState:
    return await self._call_and_record(
        self._computer.scroll_at, x, y, direction, magnitude
    )

  @override
  async def wait(self, seconds: int) -> ComputerState:
    return await self._call_and_record(self._computer.wait, seconds)

  @override
  async def go_back(self) -> ComputerState:
    return await self._call_and_record(self._computer.go_back)

  @override
  async def go_forward(self) -> ComputerState:
    return await self._call_and_record(self._computer.go_forward)

  @override
  async def search(self) -> ComputerState:
    return await self._call_and_record(self._computer.search)

  @override
  async def navigate(self, url: str) -> ComputerState:
    return await self._call_and_record(self._computer.navigate, url)

  @override
  async def key_combination(self, keys: list[str]) -> ComputerState:
    return await self._call_and_record(self._computer.key_combination, keys)

  @override
  async def drag_and_drop(
      self, x: int, y: int, destination_x: int, destination_y: int
  ) -> ComputerState:
    return await self._call_and_record(
        self._computer.drag_and_drop, x, y, destination_x, destination_y
    )

  @override
  async def current_state(self) -> ComputerState:
    return await self._call_and_record(self._computer.current_state)

  @override
  async def initialize(self) -> None:
    await self._computer.initialize()

  @override
  async def close(self) -> None:
    try:
      await self.finalize_current_recording()
    finally:
      await self._computer.close()

  @override
  async def environment(self) -> ComputerEnvironment:
    return await self._computer.environment()

  async def aclose(self) -> None:
    await self._client.aclose()


def wrap_playwright_computer(
    computer: BaseComputer,
    *,
    config: Optional[RrwebCloudReplayConfig] = None,
    client: Optional[RrwebCloudApiClient] = None,
) -> RrwebCloudPlaywrightComputer:
  return RrwebCloudPlaywrightComputer(
      computer,
      config=config,
      client=client,
  )


def _current_trace_id() -> str | None:
  span = trace.get_current_span()
  span_context = span.get_span_context()
  if not span_context or not span_context.is_valid:
    return None
  return format(span_context.trace_id, "032x")
