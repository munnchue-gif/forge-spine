"""
Forge Spine — FabricGate v2

Forward-declared pathway registry + three-axis evaluation
(identity seal × capability × epoch) + silence on undeclared paths
+ O(1) vessel revocation for Hopper events.

Public interface (Kernel-compatible):
  sign / authorize / enforce / stats / ledger_size
  register_pathway / deregister_pathway / list_pathways / pathway_registered
  revoke_vessel / clear_revocation
"""

from __future__ import annotations

import hmac
import struct
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable, ClassVar, Protocol


class Role(str, Enum):
    KERNEL = "kernel"
    OVERSEER = "overseer"
    MODEL = "model"
    EXTERNAL = "external"

    @property
    def may_inspect_registry(self) -> bool:
        return self in (Role.KERNEL, Role.OVERSEER)

    @property
    def may_modify_registry(self) -> bool:
        return self is Role.KERNEL


class Capability(Protocol):
    kind: str
    def canonical(self) -> str: ...


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class ClearanceLevel(int, Enum):
    PUBLIC = 0
    TRUSTED = 10
    PRIVILEGED = 20
    SOVEREIGN = 30


@dataclass(frozen=True, slots=True)
class PathwayDescriptor:
    kind: str
    direction: Direction = Direction.INTERNAL
    min_clearance: ClearanceLevel = ClearanceLevel.TRUSTED
    description: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.kind or self.kind != self.kind.strip() or " " in self.kind:
            raise ValueError(f"invalid pathway kind: {self.kind!r}")


class PathwayRegistry:
    class _Missing:
        _instance: ClassVar[PathwayRegistry._Missing | None] = None
        def __new__(cls) -> PathwayRegistry._Missing:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    MISSING: ClassVar[PathwayRegistry._Missing]

    def __init__(self) -> None:
        self._registry: dict[str, PathwayDescriptor] = {}

    def register(self, pathway: PathwayDescriptor, *, role: Role) -> None:
        if not role.may_modify_registry:
            raise PermissionError(f"Role {role.value!r} may not register pathways")
        self._registry[pathway.kind] = pathway

    def deregister(self, kind: str, *, role: Role) -> None:
        if not role.may_modify_registry:
            raise PermissionError(f"Role {role.value!r} may not deregister pathways")
        self._registry.pop(kind, None)

    def _lookup(self, kind: str) -> PathwayDescriptor | PathwayRegistry._Missing:
        return self._registry.get(kind, PathwayRegistry.MISSING)

    def list_pathways(self, *, role: Role) -> tuple[PathwayDescriptor, ...]:
        if not role.may_inspect_registry:
            raise PermissionError(f"Role {role.value!r} may not inspect registry")
        return tuple(self._registry.values())

    def pathway_registered(self, kind: str, *, role: Role) -> bool:
        if not role.may_inspect_registry:
            raise PermissionError(f"Role {role.value!r} may not inspect registry")
        return kind in self._registry

    def __len__(self) -> int:
        return len(self._registry)


PathwayRegistry.MISSING = PathwayRegistry._Missing()


class Decision(Enum):
    ALLOW = "allow"
    DENY_SIGNATURE = "deny_signature"
    DENY_EXPIRED = "deny_expired"
    DENY_REPLAY = "deny_replay"
    DENY_POLICY = "deny_policy"
    DENY_PATH_NOT_DECLARED = "deny_path_not_declared"
    DENY_PATH_SUSPENDED = "deny_path_suspended"
    DENY_REVOKED = "deny_revoked"


@dataclass(frozen=True, slots=True)
class SignedCapability:
    kind: str
    canonical: str
    token: str
    issued_at: float
    nonce: str = ""
    vessel_id: str = ""


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision: Decision
    kind: str
    audit_id: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    def enforce(self) -> str:
        if not self.allowed:
            raise GateDenied(self)
        return self.audit_id


class GateDenied(Exception):
    def __init__(self, d: GateDecision) -> None:
        self.decision = d
        super().__init__(f"{d.decision.value}: {d.reason} [{d.kind} audit={d.audit_id}]")


class ReplayLedger:
    __slots__ = ("_buckets", "_window", "_tolerance", "_keep")

    def __init__(self, window_seconds: int, tolerance: int) -> None:
        self._window = window_seconds
        self._tolerance = tolerance
        self._keep = (2 * tolerance) + 3
        self._buckets: dict[int, set[bytes]] = {}

    def _bucket_of(self, ts: float) -> int:
        return int(ts) // self._window

    def _gc(self, now_bucket: int) -> None:
        cutoff = now_bucket - self._keep
        for b in [b for b in self._buckets if b < cutoff]:
            del self._buckets[b]

    def check_and_record(self, token_digest: bytes, now: float) -> bool:
        nb = self._bucket_of(now)
        self._gc(nb)
        for b in range(nb - self._tolerance - 1, nb + self._tolerance + 2):
            if token_digest in self._buckets.get(b, ()):
                return False
        self._buckets.setdefault(nb, set()).add(token_digest)
        return True

    def size(self) -> int:
        return sum(len(s) for s in self._buckets.values())


@dataclass
class GateStats:
    allowed: int = 0
    denied_signature: int = 0
    denied_expired: int = 0
    denied_replay: int = 0
    denied_policy: int = 0
    denied_path_not_declared: int = 0
    denied_path_suspended: int = 0
    denied_revoked: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "allowed": self.allowed,
            "denied_signature": self.denied_signature,
            "denied_expired": self.denied_expired,
            "denied_replay": self.denied_replay,
            "denied_policy": self.denied_policy,
            "denied_path_not_declared": self.denied_path_not_declared,
            "denied_path_suspended": self.denied_path_suspended,
            "denied_revoked": self.denied_revoked,
        }

    def _bump(self, decision: Decision) -> None:
        match decision:
            case Decision.ALLOW: self.allowed += 1
            case Decision.DENY_SIGNATURE: self.denied_signature += 1
            case Decision.DENY_EXPIRED: self.denied_expired += 1
            case Decision.DENY_REPLAY: self.denied_replay += 1
            case Decision.DENY_POLICY: self.denied_policy += 1
            case Decision.DENY_PATH_NOT_DECLARED: self.denied_path_not_declared += 1
            case Decision.DENY_PATH_SUSPENDED: self.denied_path_suspended += 1
            case Decision.DENY_REVOKED: self.denied_revoked += 1


class FabricGate:
    def __init__(
        self,
        secret: bytes | None = None,
        *,
        key_resolver: Callable[[str], bytes] | None = None,
        window_seconds: int = 30,
        tolerance: int = 1,
        emit: Callable[[str, dict], None] | None = None,
        pathway_registry: PathwayRegistry | None = None,
    ) -> None:
        if secret is None and key_resolver is None:
            raise ValueError("FabricGate requires secret or key_resolver")
        self._secret = secret
        self._key_resolver = key_resolver
        self._window = window_seconds
        self._tolerance = tolerance
        self._ledger = ReplayLedger(window_seconds, tolerance)
        self._policies: list[Callable[[SignedCapability, str], str | None]] = []
        self._emit = emit or (lambda topic, payload: None)
        self._registry = pathway_registry if pathway_registry is not None else PathwayRegistry()
        self._revocation_epochs: dict[str, float] = {}
        self.stats = GateStats()

    def _key(self, tenant_id: str) -> bytes:
        if self._key_resolver is not None:
            return self._key_resolver(tenant_id)
        assert self._secret is not None
        return self._secret

    def add_policy(self, policy: Callable[[SignedCapability, str], str | None]) -> None:
        self._policies.append(policy)

    def revoke_vessel(self, vessel_id: str, *, at: float | None = None) -> None:
        if not vessel_id:
            raise ValueError("vessel_id required")
        epoch = at if at is not None else time.time()
        self._revocation_epochs[vessel_id] = epoch
        self._emit("gate.vessel_revoked", {"vessel_id": vessel_id, "epoch": epoch})

    def clear_revocation(self, vessel_id: str, *, role: Role) -> None:
        if not role.may_modify_registry:
            raise PermissionError("only KERNEL may clear revocations")
        self._revocation_epochs.pop(vessel_id, None)

    def register_pathway(self, pathway: PathwayDescriptor, *, role: Role) -> None:
        self._registry.register(pathway, role=role)

    def deregister_pathway(self, kind: str, *, role: Role) -> None:
        self._registry.deregister(kind, role=role)

    def list_pathways(self, *, role: Role) -> tuple[PathwayDescriptor, ...]:
        return self._registry.list_pathways(role=role)

    def pathway_registered(self, kind: str, *, role: Role) -> bool:
        return self._registry.pathway_registered(kind, role=role)

    def sign(
        self,
        cap: Capability,
        *,
        tenant_id: str = "default",
        vessel_id: str = "",
        ts: float | None = None,
        nonce: str | None = None,
    ) -> SignedCapability:
        issued = ts if ts is not None else time.time()
        bucket = int(issued) // self._window
        n = nonce if nonce is not None else secrets.token_hex(16)
        canonical = cap.canonical()
        msg = (
            canonical.encode()
            + b"|nonce=" + n.encode()
            + b"|vessel_id=" + vessel_id.encode()
            + struct.pack("<Q", bucket)
        )
        token = hmac.new(self._key(tenant_id), msg, sha256).hexdigest()
        return SignedCapability(
            kind=cap.kind, canonical=canonical, token=token,
            issued_at=issued, nonce=n, vessel_id=vessel_id,
        )

    def authorize(
        self,
        signed: SignedCapability,
        *,
        tenant_id: str = "default",
        vessel_id: str = "",
        now: float | None = None,
    ) -> GateDecision:
        now = now if now is not None else time.time()
        audit_id = sha256((signed.token + f"{now:.6f}").encode()).hexdigest()[:16]
        vid = vessel_id or signed.vessel_id

        def _deny(dec: Decision, reason: str, topic: str = "gate.denied") -> GateDecision:
            d = GateDecision(dec, signed.kind, audit_id, reason)
            self.stats._bump(dec)
            self._emit(topic, {"reason": dec.value, "kind": signed.kind})
            return d

        # Axis 0 — path presence (before any crypto)
        pathway = self._registry._lookup(signed.kind)
        if isinstance(pathway, PathwayRegistry._Missing):
            return _deny(Decision.DENY_PATH_NOT_DECLARED, "pathway not declared")
        if not pathway.enabled:
            return _deny(Decision.DENY_PATH_SUSPENDED, f"pathway {signed.kind!r} suspended")

        # Axis 1 — epoch
        age = now - signed.issued_at
        max_age = (self._tolerance + 1) * self._window
        if age > max_age or age < -self._window:
            return _deny(Decision.DENY_EXPIRED, f"age={age:.0f}s outside ±{max_age}s")

        # Axis 2 — identity seal
        key = self._key(tenant_id)
        body = (
            signed.canonical.encode()
            + b"|nonce=" + signed.nonce.encode()
            + b"|vessel_id=" + signed.vessel_id.encode()
        )
        now_bucket = int(now) // self._window
        seal_ok = False
        for off in range(-self._tolerance, self._tolerance + 1):
            expected = hmac.new(key, body + struct.pack("<Q", now_bucket + off), sha256).hexdigest()
            if hmac.compare_digest(expected, signed.token):
                seal_ok = True
                break
        if not seal_ok:
            return _deny(Decision.DENY_SIGNATURE, "hmac mismatch")

        # Replay
        digest = bytes.fromhex(signed.token)
        if not self._ledger.check_and_record(digest, now):
            return _deny(Decision.DENY_REPLAY, "seen before", "gate.replay_suppressed")

        # Revocation
        if vid:
            epoch = self._revocation_epochs.get(vid)
            if epoch is not None and signed.issued_at < epoch:
                return _deny(Decision.DENY_REVOKED, f"vessel {vid!r} revoked at {epoch:.3f}")

        # Policy hooks
        for policy in self._policies:
            reason = policy(signed, tenant_id)
            if reason is not None:
                return _deny(Decision.DENY_POLICY, reason)

        self.stats._bump(Decision.ALLOW)
        self._emit("gate.allowed", {"kind": signed.kind, "audit": audit_id})
        return GateDecision(Decision.ALLOW, signed.kind, audit_id)

    def enforce(self, signed: SignedCapability, *, tenant_id: str = "default",
                vessel_id: str = "", now: float | None = None) -> str:
        d = self.authorize(signed, tenant_id=tenant_id, vessel_id=vessel_id, now=now)
        if not d.allowed:
            raise GateDenied(d)
        return d.audit_id

    def ledger_size(self) -> int:
        return self._ledger.size()
