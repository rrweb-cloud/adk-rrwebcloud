from __future__ import annotations

import json
import time
from typing import Any
from typing import Optional

import httpx

from .config import RrwebCloudReplayConfig


class RrwebCloudApiClient:
  def __init__(
      self,
      config: RrwebCloudReplayConfig,
      *,
      http_client: Optional[httpx.AsyncClient] = None,
  ) -> None:
    self._config = config
    self._http_client = http_client or httpx.AsyncClient(timeout=30.0)
    self._owns_http_client = http_client is None

  def _headers(self) -> dict[str, str]:
    headers = {"content-type": "application/x-ndjson"}
    if self._config.api_key:
      headers["authorization"] = f"Bearer {self._config.api_key}"
    return headers

  async def ingest_events(
      self,
      *,
      recording_id: str,
      metadata: dict[str, Any],
      events: list[dict[str, Any]],
  ) -> None:
    payload_lines = [
        json.dumps(_metadata_event(metadata), separators=(",", ":"))
    ]
    payload_lines.extend(
        json.dumps(event, separators=(",", ":")) for event in events
    )
    response = await self._http_client.post(
        (
            f"{self._config.ingest_base_url}/recordings/"
            f"{recording_id}/ingest"
        ),
        headers=self._headers(),
        content="\n".join(payload_lines),
    )
    response.raise_for_status()

  def preview_url(self, recording_id: str) -> str:
    return f"{self._config.api_base_url}/recordings/{recording_id}/preview"

  async def aclose(self) -> None:
    if self._owns_http_client:
      await self._http_client.aclose()


def _metadata_event(metadata: dict[str, Any]) -> dict[str, Any]:
  return {
      "timestamp": int(time.time() * 1000),
      "type": 5,
      "data": {
          "tag": "recording-meta",
          "payload": metadata,
      },
  }
