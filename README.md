# adk-rrwebcloud

`adk-rrwebcloud` is a small companion package that adds rrweb Cloud session
replay to browser-based Google ADK runs.

It is designed to stay out of ADK core. You install it alongside
[`google-adk`](https://pypi.org/project/google-adk/), register the plugin on
your runner, and wrap the browser-backed `BaseComputer` you already use.

## What it does

- creates one rrweb Cloud recording per ADK invocation
- correlates each recording with ADK `session.id` and `invocation_id`
- persists replay metadata into `session.state["rrwebcloud_replay"]`
- wraps a Playwright-backed ADK `BaseComputer`
- skips the browser's initial `about:blank` page and starts recording on the
  first real navigation

## Install

```bash
pip install google-adk git+https://github.com/rrweb-cloud/adk-rrwebcloud.git
```

The package is not published on PyPI yet, so install from GitHub for now.

For local development in this workspace:

```bash
git clone https://github.com/rrweb-cloud/adk-rrwebcloud.git
cd adk-rrwebcloud
uv sync
uv run --with playwright python -m playwright install chromium
```

## Environment

Required:

- `RRWEB_CLOUD_RECORDING_PUBLIC_KEY`
- `RRWEB_CLOUD_RECORDING_SECRET_KEY`

Also supported for compatibility:

- `RRWEBCLOUD_PUBLIC_KEY`
- `RRWEBCLOUD_SECRET_KEY`

## Usage

```python
from adk_rrwebcloud import RrwebCloudReplayPlugin

plugin = RrwebCloudReplayPlugin()
wrapped_computer = plugin.wrap_computer(browser_computer)

runner = InMemoryRunner(
    agent=root_agent,
    app_name="my_browser_app",
    plugins=[plugin],
)
```

The wrapper is the browser instrumentation point. The plugin is the ADK
invocation/session persistence point. You usually need both.

## Smoke Test

This repo includes a runnable sample:

```bash
cd adk-rrwebcloud
uv run --with playwright python examples/live_smoke.py --url https://www.google.com
```

It prints JSON with the final page title, URL, and rrweb Cloud recording
metadata.

Before running it, export `RRWEB_CLOUD_RECORDING_PUBLIC_KEY` and
`RRWEB_CLOUD_RECORDING_SECRET_KEY`, or place them in a local `.env` file.

## Project Layout

- [`src/adk_rrwebcloud/__init__.py`](./src/adk_rrwebcloud/__init__.py)
- [`src/adk_rrwebcloud/plugin.py`](./src/adk_rrwebcloud/plugin.py)
- [`src/adk_rrwebcloud/computer.py`](./src/adk_rrwebcloud/computer.py)
- [`examples/live_smoke.py`](./examples/live_smoke.py)

## Why a separate project

This integration is rrweb Cloud specific. A separate package gives users a
simple install story without requiring ADK core to carry a vendor-specific
integration forever.

The likely upstream path later is narrower:

- a generic browser instrumentation hook in ADK
- documentation for third-party replay integrations
- maybe a community integration reference
