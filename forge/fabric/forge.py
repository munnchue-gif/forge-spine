"""
Forge-NG — Forge organ: the privileged creator and evolver of the fabric.

Only Kernel and Overseer may call this organ.
Every act of creation is a Capability that must pass the Gate
and is permanently recorded in the Ledger.

Public surface:
  - spawn_pathway
  - seal_organ
  - upgrade_organ
  - create_vessel
  - concoct_policy
  - list_sealed_organs / list_vessels (privileged)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


class Role(str, Enum):
    KERNEL   = "kernel"
    OVERSEER = "overseer"
    MODEL    = "model"
    EXTERNAL = "external"

    @property
    def may_forge(self) -> bool:
        return self in (Role.KERNEL, Role.OVERSEER)


class Capability(Protocol):
    kind: str
    def canonical(self) -> str: ...


@dataclass(frozen=True, slots=True)
class PathwayDescriptor:
    kind: str
    direction: str = "internal"          # inbound | outbound | internal
    min_clearance: str = "PRIVILEGED"    # PUBLIC | TRUSTED | PRIVILEGED | SOVEREIGN
    description: str = ""
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SealedOrgan:
    name: str
    version: str
    source_hash: str
    sealed_at: float
    sealed_by: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VesselSpec:
    vessel_id: str
    task: str
    capabilities: tuple[str, ...]
    clearance: str
    created_at: float
    created_by: str


@dataclass(frozen=True, slots=True)
class ForgeCapability:
    """Capability used by the Forge organ itself."""
    kind: str
    payload: str

    def canonical(self) -> str:
        return f"{self.kind}|{self.payload}"


class ForgeDenied(Exception):
    pass


class Forge:
    """
    Privileged organ that can create and evolve the fabric.

    All public methods require role=KERNEL or role=OVERSEER.
    Every successful action is recorded via the optional ledger callback.
    """

    def __init__(
        self,
        *,
        gate: Any = None,
        ledger_append: Callable[[dict], None] | None = None,
        emit: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._gate = gate
        self._ledger_append = ledger_append or (lambda entry: None)
        self._emit = emit or (lambda topic, payload: None)
        self._sealed: dict[str, SealedOrgan] = {}
        self._vessels: dict[str, VesselSpec] = {}
        self._policies: list[Callable] = []

    def _require_role(self, role: Role) -> None:
        if not role.may_forge:
            raise ForgeDenied(
                f"Role {role.value!r} may not call the Forge organ. "
                f"Only kernel and overseer are permitted."
            )

    def _record(self, action: str, detail: dict) -> None:
        entry = {
            "organ": "forge",
            "action": action,
            "ts": time.time(),
            **detail,
        }
        self._ledger_append(entry)
        self._emit(f"forge.{action}", detail)

    def _authorize(self, kind: str, payload: str, role: Role) -> str:
        if self._gate is None:
            return "no-gate"
        cap = ForgeCapability(kind=kind, payload=payload)
        signed = self._gate.sign(cap)
        decision = self._gate.authorize(signed)
        if not getattr(decision, "allowed", False):
            reason = getattr(decision, "reason", "denied")
            raise ForgeDenied(f"Gate denied {kind}: {reason}")
        return getattr(decision, "audit_id", "unknown")

    def spawn_pathway(
        self,
        pathway: PathwayDescriptor,
        *,
        role: Role,
    ) -> PathwayDescriptor:
        self._require_role(role)
        if not pathway.kind or " " in pathway.kind:
            raise ValueError("pathway.kind must be non-empty and contain no spaces")

        audit = self._authorize("forge.spawn_pathway", pathway.kind, role)

        if self._gate is not None and hasattr(self._gate, "register_pathway"):
            self._gate.register_pathway(pathway, role=role)

        self._record("spawn_pathway", {
            "kind": pathway.kind,
            "direction": pathway.direction,
            "min_clearance": pathway.min_clearance,
            "audit_id": audit,
            "by": role.value,
        })
        return pathway

    def seal_organ(
        self,
        name: str,
        source: str,
        *,
        version: str = "1.0.0",
        role: Role,
        metadata: dict | None = None,
    ) -> SealedOrgan:
        self._require_role(role)
        if not name or not source:
            raise ValueError("name and source are required")

        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        audit = self._authorize("forge.seal_organ", f"{name}:{source_hash[:16]}", role)

        organ = SealedOrgan(
            name=name,
            version=version,
            source_hash=source_hash,
            sealed_at=time.time(),
            sealed_by=role.value,
            metadata=metadata or {},
        )
        self._sealed[name] = organ

        self._record("seal_organ", {
            "name": name,
            "version": version,
            "source_hash": source_hash,
            "audit_id": audit,
            "by": role.value,
        })
        return organ

    def upgrade_organ(
        self,
        name: str,
        new_source: str,
        *,
        version: str,
        role: Role,
    ) -> SealedOrgan:
        self._require_role(role)
        if name not in self._sealed:
            raise ForgeDenied(f"Organ {name!r} has never been sealed")

        return self.seal_organ(
            name=name,
            source=new_source,
            version=version,
            role=role,
            metadata={"upgraded_from": self._sealed[name].version},
        )

    def create_vessel(
        self,
        task: str,
        capabilities: list[str],
        *,
        clearance: str = "PRIVILEGED",
        vessel_id: str | None = None,
        role: Role,
    ) -> VesselSpec:
        self._require_role(role)
        vid = vessel_id or f"vessel-{uuid.uuid4().hex[:12]}"
        audit = self._authorize("forge.create_vessel", vid, role)

        spec = VesselSpec(
            vessel_id=vid,
            task=task,
            capabilities=tuple(capabilities),
            clearance=clearance,
            created_at=time.time(),
            created_by=role.value,
        )
        self._vessels[vid] = spec

        self._record("create_vessel", {
            "vessel_id": vid,
            "task": task,
            "capabilities": list(capabilities),
            "clearance": clearance,
            "audit_id": audit,
            "by": role.value,
        })
        return spec

    def concoct_policy(
        self,
        name: str,
        policy_fn: Callable,
        *,
        role: Role,
    ) -> str:
        self._require_role(role)
        policy_id = f"policy-{name}-{uuid.uuid4().hex[:8]}"
        audit = self._authorize("forge.concoct_policy", policy_id, role)

        self._policies.append(policy_fn)
        if self._gate is not None and hasattr(self._gate, "add_policy"):
            self._gate.add_policy(policy_fn)

        self._record("concoct_policy", {
            "policy_id": policy_id,
            "name": name,
            "audit_id": audit,
            "by": role.value,
        })
        return policy_id

    def list_sealed_organs(self, *, role: Role) -> tuple[SealedOrgan, ...]:
        self._require_role(role)
        return tuple(self._sealed.values())

    def list_vessels(self, *, role: Role) -> tuple[VesselSpec, ...]:
        self._require_role(role)
        return tuple(self._vessels.values())
