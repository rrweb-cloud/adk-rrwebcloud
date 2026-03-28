from __future__ import annotations

import os
from typing import Any
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

DEFAULT_API_BASE_URL = "https://api.rrwebcloud.com"
DEFAULT_INGEST_BASE_URL = "https://api.rrwebcloud.com"
DEFAULT_RRWEB_CDN_URL = "https://cdn.jsdelivr.net/npm/rrweb@latest/dist/rrweb.min.js"


def _env_flag(name: str, default: bool) -> bool:
  raw_value = os.getenv(name)
  if raw_value is None:
    return default
  return raw_value.strip().lower() not in {"0", "false", "no", "off"}


class RrwebCloudReplayConfig(BaseModel):
  model_config = ConfigDict(populate_by_name=True, extra="forbid")

  api_key: Optional[str] = Field(default=None, alias="public_key")
  secret_key: Optional[str] = None
  enabled: bool = True
  persist_to_session: bool = True
  api_base_url: str = DEFAULT_API_BASE_URL
  ingest_base_url: str = DEFAULT_INGEST_BASE_URL
  rrweb_cdn_url: str = DEFAULT_RRWEB_CDN_URL
  block_class: str = "rr-block"
  mask_text_class: str = "rr-mask"
  flush_events_at: int = 200

  @model_validator(mode="after")
  def _normalize_urls(self) -> "RrwebCloudReplayConfig":
    self.api_base_url = self.api_base_url.rstrip("/")
    self.ingest_base_url = self.ingest_base_url.rstrip("/")
    return self

  @property
  def is_configured(self) -> bool:
    return bool(self.api_key)

  @property
  def should_capture(self) -> bool:
    return self.enabled and self.is_configured

  @classmethod
  def from_env(cls, **overrides: Any) -> "RrwebCloudReplayConfig":
    data = {
        "api_key": os.getenv("RRWEB_CLOUD_RECORDING_PUBLIC_KEY")
        or os.getenv("RRWEBCLOUD_API_KEY")
        or os.getenv("RRWEBCLOUD_PUBLIC_KEY"),
        "secret_key": os.getenv("RRWEB_CLOUD_RECORDING_SECRET_KEY")
        or os.getenv("RRWEBCLOUD_SECRET_KEY"),
        "enabled": _env_flag("RRWEBCLOUD_ENABLED", True),
        "persist_to_session": _env_flag(
            "RRWEBCLOUD_PERSIST_TO_SESSION", True
        ),
        "api_base_url": os.getenv(
            "RRWEBCLOUD_API_BASE_URL", DEFAULT_API_BASE_URL
        ),
        "ingest_base_url": os.getenv(
            "RRWEBCLOUD_INGEST_BASE_URL", DEFAULT_INGEST_BASE_URL
        ),
        "rrweb_cdn_url": os.getenv(
            "RRWEBCLOUD_RRWEB_CDN_URL", DEFAULT_RRWEB_CDN_URL
        ),
    }
    data.update(overrides)
    return cls.model_validate(data)
