"""
Forge Spine — Isolation membrane.

Capability scopes + levels, Envelope grants, vessel binding.
Hopper calls revoke via Gate.revoke_vessel.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CapClass(str, Enum):
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    GPU = "gpu"
    CPU = "cpu"
    MEMORY = "memory"
    MODEL = "model"
    HUB = "hub"


class CapLevel(int, Enum):
    NONE = 0
    READ = 10
    WRITE = 20
    FULL = 30


class VesselState(str, Enum):
    SPAWNING = "spawning"
    RUNNING = "running"
    HOPPING = "hopping"
    VOID = "void"


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    cls: CapClass
    level: CapLevel


@dataclass
class Envelope:
    vessel_id: str
    grants: dict[CapClass, CapLevel] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    state: VesselState = VesselState.SPAWNING
    meta: dict[str, Any] = field(default_factory=dict)

    def allow(self, cls: CapClass, need: CapLevel) -> bool:
        have = self.grants.get(cls, CapLevel.NONE)
        return int(have) >= int(need)

    def set_grant(self, cls: CapClass, level: CapLevel) -> None:
        self.grants[cls] = level

    def revoke_all(self) -> None:
        self.grants.clear()


class IsolationMembrane:
    """
    Tracks envelopes per vessel. Kernel-compatible.
    ledger_record: optional Callable[[topic, payload], None]
    """

    def __init__(
        self,
        *,
        gate: Any = None,
        ledger_record: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._gate = gate
        self._ledger = ledger_record or (lambda t, p: None)
        self._envelopes: dict[str, Envelope] = {}

    def spawn(
        self,
        *,
        vessel_id: str | None = None,
        grants: list[CapabilityGrant] | None = None,
        meta: dict | None = None,
    ) -> Envelope:
        vid = vessel_id or f"vessel-{uuid.uuid4().hex[:12]}"
        env = Envelope(vessel_id=vid, meta=meta or {})
        for g in grants or []:
            env.set_grant(g.cls, g.level)
        env.state = VesselState.RUNNING
        self._envelopes[vid] = env
        self._ledger("isolation.spawn", {"vessel_id": vid, "grants": {
            k.value: v.value for k, v in env.grants.items()
        }})
        return env

    def get(self, vessel_id: str) -> Envelope | None:
        return self._envelopes.get(vessel_id)

    def check(self, vessel_id: str, cls: CapClass, need: CapLevel) -> bool:
        env = self._envelopes.get(vessel_id)
        if env is None or env.state != VesselState.RUNNING:
            return False
        return env.allow(cls, need)

    def mark_hopping(self, vessel_id: str) -> None:
        env = self._envelopes.get(vessel_id)
        if env:
            env.state = VesselState.HOPPING

    def mark_void(self, vessel_id: str) -> None:
        env = self._envelopes.get(vessel_id)
        if env:
            env.state = VesselState.VOID
            env.revoke_all()

    def list_running(self) -> list[str]:
        return [v for v, e in self._envelopes.items() if e.state == VesselState.RUNNING]
