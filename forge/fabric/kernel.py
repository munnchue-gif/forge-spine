"""
Forge Spine — Kernel (Ledger-integrated).

Boot order:
  1. AuditLedger
  2. FabricGate (emit → ledger.record)
  3. Forge
  4. CapsuleStore
  5. HubSocket
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from forge.fabric.ledger import AuditLedger
from forge.fabric.gate import (
    FabricGate,
    PathwayDescriptor as GatePathway,
    Direction,
    ClearanceLevel,
    Role as GateRole,
)
from forge.fabric.forge import Forge, Role, PathwayDescriptor
from forge.fabric.capsule import CapsuleStore
from forge.fabric.hub import HubSocket

logger = logging.getLogger("forge.kernel")


@dataclass
class KernelStats:
    booted: bool = False
    boot_ts: float = 0.0
    organs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "booted": self.booted,
            "boot_ts": self.boot_ts,
            "organs": list(self.organs),
        }


class ForgeKernel:
    def __init__(
        self,
        secret: bytes | None = None,
        *,
        ledger_path: str | None = None,
    ) -> None:
        if secret is None:
            env = os.environ.get("FORGE_SECRET")
            if env:
                secret = sha256(env.encode()).digest()
            else:
                secret = sha256(b"forge-spine-dev-only").digest()
                logger.warning("using DEV secret — set FORGE_SECRET in production")
        self._secret = secret
        self._ledger_path = ledger_path or os.environ.get(
            "FORGE_LEDGER_PATH", "/tmp/forge-spine-ledger.jsonl"
        )

        self.ledger: AuditLedger | None = None
        self.gate: FabricGate | None = None
        self.forge: Forge | None = None
        self.capsules: CapsuleStore | None = None
        self.hub: HubSocket | None = None
        self.stats = KernelStats()

    def _ledger_emit(self, topic: str, payload: dict) -> None:
        if self.ledger is None:
            return
        try:
            self.ledger.record(topic, payload)
        except Exception:
            logger.exception("ledger.record failed for %s", topic)

    def boot(self, gate: Any = None) -> "ForgeKernel":
        if self.stats.booted:
            raise RuntimeError("kernel already booted")

        # 1. Ledger first
        self.ledger = AuditLedger(self._ledger_path)
        logger.info("AuditLedger ready size=%s", self.ledger.size())

        # 2. Gate — emit every decision topic into ledger
        if gate is not None:
            self.gate = gate
        else:
            self.gate = FabricGate(
                secret=self._secret,
                emit=self._ledger_emit,
            )

        # 3. Forge — ledger_append maps to record
        def _forge_append(entry: dict) -> None:
            action = entry.get("action", "forge.event")
            self._ledger_emit(f"forge.{action}", entry)

        self.forge = Forge(
            gate=self.gate,
            ledger_append=_forge_append,
            emit=self._ledger_emit,
        )

        # 4–5. Capsules + Hub
        self.capsules = CapsuleStore()
        self.hub = HubSocket()

        # Seed core pathways (Gate PathwayDescriptor + enums)
        core = [
            GatePathway("forge.spawn_pathway", Direction.INTERNAL, ClearanceLevel.SOVEREIGN, "Spawn pathway"),
            GatePathway("forge.seal_organ", Direction.INTERNAL, ClearanceLevel.SOVEREIGN, "Seal organ"),
            GatePathway("forge.create_vessel", Direction.INTERNAL, ClearanceLevel.PRIVILEGED, "Create vessel"),
            GatePathway("forge.concoct_policy", Direction.INTERNAL, ClearanceLevel.SOVEREIGN, "Concoct policy"),
            GatePathway("capsule.expand", Direction.INTERNAL, ClearanceLevel.TRUSTED, "Expand capsule"),
            GatePathway("hub.register", Direction.INTERNAL, ClearanceLevel.PRIVILEGED, "Register hub"),
            GatePathway("isolation.spawn", Direction.INTERNAL, ClearanceLevel.PRIVILEGED, "Spawn envelope"),
            GatePathway("hopper.fire", Direction.INTERNAL, ClearanceLevel.SOVEREIGN, "Fire hopper"),
        ]
        for p in core:
            try:
                self.gate.register_pathway(p, role=GateRole.KERNEL)
            except Exception as e:
                logger.debug("pathway seed skipped: %s (%s)", p.kind, e)

        self.ledger.record("kernel.booted", {"ts": time.time()})
        self.stats.booted = True
        self.stats.boot_ts = time.time()
        self.stats.organs = ["ledger", "gate", "forge", "capsules", "hub"]
        logger.info("Forge Spine kernel booted: %s", self.stats.organs)
        return self

    def health(self) -> dict[str, Any]:
        if not self.stats.booted:
            return {"booted": False}
        out: dict[str, Any] = {
            **self.stats.as_dict(),
            "uptime_s": round(time.time() - self.stats.boot_ts, 3),
            "capsules": len(self.capsules.list()) if self.capsules else 0,
            "hubs": len(self.hub.list()) if self.hub else 0,
            "gate_present": self.gate is not None,
            "ledger_size": self.ledger.size() if self.ledger else 0,
            "ledger_head": self.ledger.head() if self.ledger else None,
        }
        if self.gate is not None and hasattr(self.gate, "stats"):
            out["gate_stats"] = self.gate.stats.as_dict()
        return out

    def shutdown(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ledger_verified": False,
            "ledger_error": None,
            "ledger_size": 0,
            "uptime_s": 0.0,
        }
        if not self.stats.booted:
            result["ledger_error"] = "kernel was not booted"
            return result

        uptime = round(time.time() - self.stats.boot_ts, 3)
        result["uptime_s"] = uptime
        if self.ledger:
            try:
                self.ledger.record("kernel.stopping", {"uptime_s": uptime})
            except Exception:
                pass
            result["ledger_size"] = self.ledger.size()
            try:
                vr = self.ledger.verify()
                result["ledger_verified"] = bool(vr)
                if not vr.ok:
                    result["ledger_error"] = vr.as_dict()
            except Exception as exc:
                result["ledger_error"] = str(exc)

        self.stats.booted = False
        logger.info("Forge Spine kernel shutdown verified=%s", result["ledger_verified"])
        return result


def boot_forge(
    secret: bytes | None = None,
    gate: Any = None,
    *,
    ledger_path: str | None = None,
) -> ForgeKernel:
    """Entry point: boot_forge() → running kernel."""
    return ForgeKernel(secret=secret, ledger_path=ledger_path).boot(gate=gate)
