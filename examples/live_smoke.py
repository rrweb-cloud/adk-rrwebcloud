from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from dotenv import load_dotenv
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from adk_rrwebcloud import RrwebCloudReplayPlugin
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.computer_use.base_computer import BaseComputer
from google.adk.tools.computer_use.base_computer import ComputerEnvironment
from google.adk.tools.computer_use.base_computer import ComputerState

load_dotenv(ROOT.parent / ".env", override=True)


class SmokeComputer(BaseComputer):
  def __init__(self):
    self._pw = None
    self._browser = None
    self._context = None
    self.page = None
    self.context = None
    self._dimension = (1280, 720)

  async def screen_size(self) -> tuple[int, int]:
    return self._dimension

  async def _state(self) -> ComputerState:
    screenshot = await self.page.screenshot(full_page=False) if self.page else b""
    url = self.page.url if self.page else None
    return ComputerState(screenshot=screenshot, url=url)

  async def open_web_browser(self) -> ComputerState:
    if self.page is None:
      self._pw = await async_playwright().start()
      self._browser = await self._pw.chromium.launch(headless=True)
      self._context = await self._browser.new_context(
          viewport={"width": 1280, "height": 720}
      )
      self.context = self._context
      self.page = await self._context.new_page()
    return await self._state()

  async def click_at(self, x: int, y: int) -> ComputerState:
    await self.page.mouse.click(x, y)
    return await self._state()

  async def hover_at(self, x: int, y: int) -> ComputerState:
    await self.page.mouse.move(x, y)
    return await self._state()

  async def type_text_at(self, x: int, y: int, text: str, press_enter: bool = True, clear_before_typing: bool = True) -> ComputerState:
    await self.page.mouse.click(x, y)
    if clear_before_typing:
      await self.page.keyboard.press("Meta+A")
    await self.page.keyboard.type(text)
    if press_enter:
      await self.page.keyboard.press("Enter")
    return await self._state()

  async def scroll_document(self, direction: str) -> ComputerState:
    delta = 700 if direction.lower() == "down" else -700
    await self.page.mouse.wheel(0, delta)
    return await self._state()

  async def scroll_at(self, x: int, y: int, direction: str, magnitude: int) -> ComputerState:
    await self.page.mouse.move(x, y)
    delta = magnitude if direction.lower() in ("down", "right") else -magnitude
    if direction.lower() in ("up", "down"):
      await self.page.mouse.wheel(0, delta)
    else:
      await self.page.mouse.wheel(delta, 0)
    return await self._state()

  async def wait(self, seconds: int) -> ComputerState:
    await asyncio.sleep(seconds)
    return await self._state()

  async def go_back(self) -> ComputerState:
    await self.page.go_back()
    return await self._state()

  async def go_forward(self) -> ComputerState:
    await self.page.go_forward()
    return await self._state()

  async def search(self) -> ComputerState:
    await self.page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
    return await self._state()

  async def navigate(self, url: str) -> ComputerState:
    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
    return await self._state()

  async def key_combination(self, keys: list[str]) -> ComputerState:
    for key in keys:
      await self.page.keyboard.press(key)
    return await self._state()

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> ComputerState:
    await self.page.mouse.move(x, y)
    await self.page.mouse.down()
    await self.page.mouse.move(destination_x, destination_y)
    await self.page.mouse.up()
    return await self._state()

  async def current_state(self) -> ComputerState:
    return await self._state()

  async def initialize(self) -> None:
    return None

  async def close(self) -> None:
    if self._context is not None:
      await self._context.close()
    if self._browser is not None:
      await self._browser.close()
    if self._pw is not None:
      await self._pw.stop()

  async def environment(self) -> ComputerEnvironment:
    return ComputerEnvironment.ENVIRONMENT_BROWSER


class SmokeAgent(BaseAgent):
  def __init__(self):
    super().__init__(name="rrwebcloud_smoke_agent", sub_agents=[])

  async def _run_async_impl(self, invocation_context: InvocationContext):
    del invocation_context
    yield Event(invocation_id="unused", author=self.name)


async def main_async(url: str) -> None:
  session_service = InMemorySessionService()
  session = await session_service.create_session(
      app_name="adk_rrwebcloud_smoke",
      user_id="sample_user",
      session_id="adk-rrwebcloud-smoke-session",
  )
  invocation_context = InvocationContext(
      artifact_service=None,
      session_service=session_service,
      memory_service=None,
      credential_service=None,
      invocation_id="adk-rrwebcloud-smoke-invocation",
      agent=SmokeAgent(),
      user_content=None,
      session=session,
  )

  plugin = RrwebCloudReplayPlugin()
  wrapped = plugin.wrap_computer(SmokeComputer())
  await plugin.before_run_callback(invocation_context=invocation_context)
  try:
    await wrapped.open_web_browser()
    await wrapped.navigate(url)
    await wrapped.wait(3)
    await wrapped.scroll_document("down")
    await wrapped.wait(1)
    await plugin.after_run_callback(invocation_context=invocation_context)
    print(json.dumps(session.state.get("rrwebcloud_replay")))
  finally:
    await wrapped.close()
    await plugin.close()


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--url", default="https://www.google.com")
  args = parser.parse_args()
  asyncio.run(main_async(args.url))


if __name__ == "__main__":
  main()
