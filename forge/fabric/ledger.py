"""
Forge Spine — AuditLedger v3

Hash-chained, append-only forensic ledger.
- JSONL + fsync
- Structural SHA-256 chain (previous_hash links)
- Optional HMAC author_seal (orthogonal to structural hash)
- epoch_snapshot() checkpoints
- public_log() AI-safe view
- Thread-safe (RLock)
- Gate emit compatible: record(topic, payload) -> entry_id
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

EmitHook = Callable[[str, str], None]  # (topic, entry_id)


class LedgerError(Exception):
    pass


class CorruptJournalError(LedgerError):
    pass


@dataclass(frozen=True)
class LedgerEntry:
    index: int
    entry_id: str
    topic: str
    payload: dict[str, Any]
    ts: float
    previous_hash: str
    entry_hash: str
    author_seal: str = ""
    version: int = 1

    def public_summary(self) -> dict[str, Any]:
        fp = hashlib.sha256(
            json.dumps(self.payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return {
            "index": self.index,
            "entry_id": self.entry_id,
            "topic": self.topic,
            "ts": self.ts,
            "payload_fingerprint": fp,
            "entry_hash": self.entry_hash[:16],
            "previous_hash": self.previous_hash[:16],
        }


@dataclass
class ChainBreak:
    pos: int
    kind: str
    detail: str


@dataclass
class VerificationResult:
    ok: bool
    breaks: list[ChainBreak] = field(default_factory=list)
    checked: int = 0

    def __bool__(self) -> bool:
        return self.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "breaks": [{"pos": b.pos, "kind": b.kind, "detail": b.detail} for b in self.breaks],
        }


def _canonical(index: int, entry_id: str, topic: str, payload: dict,
               ts: float, previous_hash: str, version: int) -> bytes:
    doc = {
        "entry_id": entry_id,
        "index": index,
        "payload": payload,
        "previous_hash": previous_hash,
        "topic": topic,
        "ts": ts,
        "version": version,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_chain(chain: Sequence[LedgerEntry]) -> VerificationResult:
    breaks: list[ChainBreak] = []
    if not chain:
        return VerificationResult(ok=True, breaks=[], checked=0)

    for i, e in enumerate(chain):
        if e.index != i:
            breaks.append(ChainBreak(i, "index_discontinuity", f"expected index {i}, got {e.index}"))

        if i == 0:
            if e.previous_hash != ("0" * 64):
                breaks.append(ChainBreak(i, "genesis_prev", "genesis previous_hash must be 64 zero hex"))
        else:
            if e.previous_hash != chain[i - 1].entry_hash:
                breaks.append(ChainBreak(
                    i, "chain_link_broken",
                    f"previous_hash != entry[{i-1}].entry_hash",
                ))

        expected = _hash_bytes(_canonical(
            e.index, e.entry_id, e.topic, e.payload, e.ts, e.previous_hash, e.version
        ))
        if expected != e.entry_hash:
            breaks.append(ChainBreak(i, "hash_mismatch", "recomputed hash != stored entry_hash"))

    return VerificationResult(ok=len(breaks) == 0, breaks=breaks, checked=len(chain))


class _Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: LedgerEntry) -> None:
        line = json.dumps({
            "index": entry.index,
            "entry_id": entry.entry_id,
            "topic": entry.topic,
            "payload": entry.payload,
            "ts": entry.ts,
            "previous_hash": entry.previous_hash,
            "entry_hash": entry.entry_hash,
            "author_seal": entry.author_seal,
            "version": entry.version,
        }, default=str) + "\n"
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def load(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        out: list[LedgerEntry] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    out.append(LedgerEntry(
                        index=int(d["index"]),
                        entry_id=str(d["entry_id"]),
                        topic=str(d["topic"]),
                        payload=dict(d.get("payload") or {}),
                        ts=float(d["ts"]),
                        previous_hash=str(d["previous_hash"]),
                        entry_hash=str(d["entry_hash"]),
                        author_seal=str(d.get("author_seal") or ""),
                        version=int(d.get("version", 1)),
                    ))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                    raise CorruptJournalError(f"line {lineno}: {e}") from e
        return out


class AuditLedger:
    """
    Minimal Kernel-facing surface:
      record(topic, payload) -> entry_id
      verify() -> VerificationResult
      epoch_snapshot(label) -> snapshot_id
      public_log(limit=N) -> list[dict]
      size() / head()
    """

    GENESIS_PREV = "0" * 64

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        hmac_secret: bytes | None = None,
        on_record: EmitHook | None = None,
    ) -> None:
        self._path = Path(path) if path else Path(
            os.environ.get("FORGE_LEDGER_PATH", "/tmp/forge-spine-ledger.jsonl")
        )
        self._hmac_secret = hmac_secret
        self._on_record = on_record
        self._lock = threading.RLock()
        self._journal = _Journal(self._path)
        self._chain: list[LedgerEntry] = []

        loaded = self._journal.load()
        if loaded:
            result = _verify_chain(loaded)
            if not result.ok:
                raise CorruptJournalError(f"loaded chain invalid: {result.as_dict()}")
            self._chain = loaded
        else:
            self._write_genesis()

    def _write_genesis(self) -> None:
        entry_id = "genesis-" + uuid.uuid4().hex[:12]
        ts = time.time()
        topic = "ledger.genesis"
        payload = {"note": "chain start"}
        prev = self.GENESIS_PREV
        index = 0
        entry_hash = _hash_bytes(_canonical(index, entry_id, topic, payload, ts, prev, 1))
        seal = self._seal(entry_hash)
        entry = LedgerEntry(
            index=index, entry_id=entry_id, topic=topic, payload=payload,
            ts=ts, previous_hash=prev, entry_hash=entry_hash, author_seal=seal,
        )
        self._commit_raw(entry)

    def _seal(self, entry_hash: str) -> str:
        if not self._hmac_secret:
            return ""
        return hmac.new(self._hmac_secret, entry_hash.encode(), hashlib.sha256).hexdigest()

    def _fire_hook(self, topic: str, entry_id: str) -> None:
        if self._on_record is None:
            return
        try:
            self._on_record(topic, entry_id)
        except Exception:
            pass

    def _commit_raw(self, entry: LedgerEntry) -> None:
        """Disk before memory. Caller holds self._lock when needed."""
        with self._lock:
            self._journal.append(entry)
            self._chain.append(entry)

    def record(self, topic: str, payload: Any = None) -> str:
        if not topic or not str(topic).strip():
            raise ValueError("topic must be non-empty")
        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            payload = {"value": payload}

        with self._lock:
            index = len(self._chain)
            prev = self._chain[-1].entry_hash if self._chain else self.GENESIS_PREV
            entry_id = uuid.uuid4().hex
            ts = time.time()
            entry_hash = _hash_bytes(_canonical(
                index, entry_id, topic, payload, ts, prev, 1
            ))
            seal = self._seal(entry_hash)
            entry = LedgerEntry(
                index=index, entry_id=entry_id, topic=topic, payload=payload,
                ts=ts, previous_hash=prev, entry_hash=entry_hash, author_seal=seal,
            )
            self._journal.append(entry)
            self._chain.append(entry)

        self._fire_hook(topic, entry_id)
        return entry_id

    def epoch_snapshot(self, label: str = "") -> str:
        with self._lock:
            head = self._chain[-1]
            payload = {
                "label": label,
                "head_index": head.index,
                "head_hash": head.entry_hash,
                "size": len(self._chain),
            }
            index = len(self._chain)
            prev = head.entry_hash
            entry_id = "snap-" + uuid.uuid4().hex[:12]
            ts = time.time()
            topic = "ledger.epoch_snapshot"
            entry_hash = _hash_bytes(_canonical(
                index, entry_id, topic, payload, ts, prev, 1
            ))
            seal = self._seal(entry_hash)
            entry = LedgerEntry(
                index=index, entry_id=entry_id, topic=topic, payload=payload,
                ts=ts, previous_hash=prev, entry_hash=entry_hash, author_seal=seal,
            )
            self._journal.append(entry)
            self._chain.append(entry)

        self._fire_hook(topic, entry_id)
        return entry_id

    def verify(self) -> VerificationResult:
        with self._lock:
            return _verify_chain(list(self._chain))

    def public_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if limit <= 0:
                slice_ = list(self._chain)
            else:
                slice_ = list(self._chain[-limit:])
        return [e.public_summary() for e in slice_]

    def size(self) -> int:
        with self._lock:
            return len(self._chain)

    def head(self) -> str | None:
        with self._lock:
            if not self._chain:
                return None
            return self._chain[-1].entry_hash

    def get_entry(self, index: int) -> LedgerEntry:
        with self._lock:
            if index < 0 or index >= len(self._chain):
                raise IndexError(index)
            return self._chain[index]
