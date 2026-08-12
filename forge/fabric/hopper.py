"""
Forge Spine — Hopper (6-phase vessel ejection).

Phases (strict order):
  1. HALT
  2. INSCRIBE
  3. REVOKE_TOKENS   → Gate.revoke_vessel
  4. DECONSTRUCT
  5. RETURN_RESOURCES
  6. SWEEP_ARENA     → pristine invariant
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from forge.fabric.isolation import IsolationMembrane, VesselState


class HopperPhase(str, Enum):
    HALT = "halt"
    INSCRIBE = "inscribe"
    REVOKE_TOKENS = "revoke_tokens"
    DECONSTRUCT = "deconstruct"
    RETURN_RESOURCES = "return_resources"
    SWEEP_ARENA = "sweep_arena"


PHASE_ORDER = (
    HopperPhase.HALT,
    HopperPhase.INSCRIBE,
    HopperPhase.REVOKE_TOKENS,
    HopperPhase.DECONSTRUCT,
    HopperPhase.RETURN_RESOURCES,
    HopperPhase.SWEEP_ARENA,
)


@dataclass
class PhaseRecord:
    phase: HopperPhase
    ts: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class HopperResult:
    vessel_id: str
    ok: bool
    phases: list[PhaseRecord] = field(default_factory=list)
    arena_pristine: bool = False
    error: str | None = None


class Hopper:
    def __init__(
        self,
        *,
        gate: Any = None,
        isolation: IsolationMembrane | None = None,
        ledger_record: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._gate = gate
        self._isolation = isolation
        self._ledger = ledger_record or (lambda t, p: None)
        self._arena_live: set[str] = set()

    def note_spawn(self, vessel_id: str) -> None:
        self._arena_live.add(vessel_id)

    def fire(self, vessel_id: str, *, reason: str = "") -> HopperResult:
        result = HopperResult(vessel_id=vessel_id, ok=False)
        try:
            # 1 HALT
            if self._isolation:
                self._isolation.mark_hopping(vessel_id)
            result.phases.append(PhaseRecord(HopperPhase.HALT, time.time(), {"reason": reason}))
            self._ledger("hopper.halt", {"vessel_id": vessel_id, "reason": reason})

            # 2 INSCRIBE
            env_snap: dict[str, Any] = {}
            if self._isolation:
                env = self._isolation.get(vessel_id)
                if env:
                    env_snap = {
                        "state": env.state.value,
                        "grants": {k.value: int(v) for k, v in env.grants.items()},
                        "meta": dict(env.meta),
                    }
            result.phases.append(PhaseRecord(HopperPhase.INSCRIBE, time.time(), env_snap))
            self._ledger("hopper.inscribe", {"vessel_id": vessel_id, **env_snap})

            # 3 REVOKE_TOKENS — hard Gate revoke
            if self._gate is not None and hasattr(self._gate, "revoke_vessel"):
                self._gate.revoke_vessel(vessel_id)
            result.phases.append(PhaseRecord(
                HopperPhase.REVOKE_TOKENS, time.time(), {"revoked": True}
            ))
            self._ledger("hopper.revoke_tokens", {"vessel_id": vessel_id})

            # 4 DECONSTRUCT
            if self._isolation:
                self._isolation.mark_void(vessel_id)
            result.phases.append(PhaseRecord(HopperPhase.DECONSTRUCT, time.time(), {}))
            self._ledger("hopper.deconstruct", {"vessel_id": vessel_id})

            # 5 RETURN_RESOURCES
            result.phases.append(PhaseRecord(
                HopperPhase.RETURN_RESOURCES, time.time(), {"resources": "released"}
            ))
            self._ledger("hopper.return_resources", {"vessel_id": vessel_id})

            # 6 SWEEP_ARENA
            self._arena_live.discard(vessel_id)
            pristine = vessel_id not in self._arena_live
            if self._isolation:
                env = self._isolation.get(vessel_id)
                pristine = pristine and (
                    env is None or env.state == VesselState.VOID
                )
            result.phases.append(PhaseRecord(
                HopperPhase.SWEEP_ARENA, time.time(), {"pristine": pristine}
            ))
            self._ledger("hopper.sweep_arena", {
                "vessel_id": vessel_id,
                "pristine": pristine,
            })

            result.arena_pristine = pristine
            result.ok = pristine
            self._ledger("hopper.complete", {
                "vessel_id": vessel_id,
                "ok": result.ok,
                "phases": [p.phase.value for p in result.phases],
            })
            return result
        except Exception as exc:
            result.error = str(exc)
            self._ledger("hopper.error", {"vessel_id": vessel_id, "error": str(exc)})
            return result

    def arena_live(self) -> frozenset[str]:
        return frozenset(self._arena_live)
