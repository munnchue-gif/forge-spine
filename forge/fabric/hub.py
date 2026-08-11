"""
Forge Spine — Hub socket.

Connection point for external tool hubs and repos (n8n, Intel/OpenVINO
tooling, local model registries, git tool capsules, etc.).

Design:
  - Hubs are registered by URL or local path
  - Tools from a hub are preferred as Capsules (download → register → expand)
  - No permanent install path; everything can collapse
  - Hub itself never gets KERNEL role
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class HubEntry:
    name: str
    kind: str                    # "git" | "http" | "local" | "n8n" | "intel" | "model"
    location: str                # url or path
    registered_at: float
    metadata: dict[str, Any] = field(default_factory=dict)


class HubError(Exception):
    pass


class HubSocket:
    """
    Registry of external hubs. Does not execute tools itself.
    Execution goes: Hub → CapsuleStore.register → expand → run under Gate.
    """

    def __init__(self) -> None:
        self._hubs: dict[str, HubEntry] = {}

    def register(
        self,
        name: str,
        *,
        kind: str,
        location: str,
        metadata: dict | None = None,
    ) -> HubEntry:
        if not name or not location:
            raise HubError("name and location required")
        entry = HubEntry(
            name=name,
            kind=kind,
            location=location,
            registered_at=time.time(),
            metadata=metadata or {},
        )
        self._hubs[name] = entry
        return entry

    def get(self, name: str) -> HubEntry:
        if name not in self._hubs:
            raise HubError(f"hub not registered: {name}")
        return self._hubs[name]

    def list(self) -> tuple[HubEntry, ...]:
        return tuple(self._hubs.values())

    def unregister(self, name: str) -> None:
        self._hubs.pop(name, None)

    # Convenience presets the user can call later
    def register_n8n(self, base_url: str = "http://127.0.0.1:5678") -> HubEntry:
        return self.register("n8n", kind="n8n", location=base_url)

    def register_local_models(self, path: str | Path) -> HubEntry:
        return self.register("local-models", kind="model", location=str(path))

    def register_intel_openvino(self, path: str | Path | None = None) -> HubEntry:
        loc = str(path) if path else "openvino-default"
        return self.register("intel-npu", kind="intel", location=loc,
                             metadata={"role": "npu-observer-leg"})
