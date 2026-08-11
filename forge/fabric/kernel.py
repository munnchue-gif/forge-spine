"""
Forge Spine — Kernel stub.

Boots the living core in dependency order:
  1. Gate (trust boundary)
  2. Forge (privileged creator)
  3. CapsuleStore (tool expand/collapse)
  4. HubSocket (external hubs)

Later organs (Ledger, Isolation, Hopper, Tailor) plug in without rewriting boot.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

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
    """
    Minimal living kernel for the spine.
    Gate is optional at construction so we can land Gate v2 next to this file.
    """

    def __init__(self, secret: bytes | None = None) -> None:
        if secret is None:
            env = os.environ.get("FORGE_SECRET")
            if env:
                secret = sha256(env.encode()).digest()
            else:
                secret = sha256(b"forge-spine-dev-only").digest()
                logger.warning("using DEV secret — set FORGE_SECRET in production")
        self._secret = secret

        self.gate: Any = None
        self.forge: Forge | None = None
        self.capsules: CapsuleStore | None = None
        self.hub: HubSocket | None = None
        self.stats = KernelStats()

    def boot(self, gate: Any = None) -> "ForgeKernel":
        if self.stats.booted:
            raise RuntimeError("kernel already booted")

        # 1. Gate (caller can inject Gate v2; otherwise we stay gate-less until wired)
        self.gate = gate

        # 2. Forge organ — privileged creator
        self.forge = Forge(gate=self.gate)

        # 3. Capsule store
        self.capsules = CapsuleStore()

        # 4. Hub socket
        self.hub = HubSocket()

        # Register core pathways if Gate supports it
        if self.gate is not None and self.forge is not None:
            core = [
                PathwayDescriptor("forge.spawn_pathway", "internal", "SOVEREIGN", "Spawn pathway"),
                PathwayDescriptor("forge.seal_organ", "internal", "SOVEREIGN", "Seal organ"),
                PathwayDescriptor("forge.create_vessel", "internal", "PRIVILEGED", "Create vessel"),
                PathwayDescriptor("forge.concoct_policy", "internal", "SOVEREIGN", "Concoct policy"),
                PathwayDescriptor("capsule.expand", "internal", "TRUSTED", "Expand capsule"),
                PathwayDescriptor("hub.register", "internal", "PRIVILEGED", "Register hub"),
            ]
            for p in core:
                try:
                    self.forge.spawn_pathway(p, role=Role.KERNEL)
                except Exception as e:
                    logger.debug("pathway seed skipped: %s (%s)", p.kind, e)

        self.stats.booted = True
        self.stats.boot_ts = time.time()
        self.stats.organs = ["gate", "forge", "capsules", "hub"]
        logger.info("Forge Spine kernel booted: %s", self.stats.organs)
        return self

    def health(self) -> dict[str, Any]:
        if not self.stats.booted:
            return {"booted": False}
        return {
            **self.stats.as_dict(),
            "capsules": len(self.capsules.list()) if self.capsules else 0,
            "hubs": len(self.hub.list()) if self.hub else 0,
            "gate_present": self.gate is not None,
        }

    def shutdown(self) -> None:
        self.stats.booted = False
        logger.info("Forge Spine kernel shutdown")


def boot_forge(secret: bytes | None = None, gate: Any = None) -> ForgeKernel:
    """Entry point: boot_forge() → running kernel."""
    return ForgeKernel(secret=secret).boot(gate=gate)
