"""
Forge Spine — Ledger validation checklist.
Run:  cd ~/forge-spine && PYTHONPATH=. python3 forge/fabric/validate_ledger.py
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from forge.fabric.ledger import (
    AuditLedger,
    CorruptJournalError,
    VerificationResult,
    _verify_chain,
)


def chk(name: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        raise AssertionError(name)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="forge-ledger-"))
    journal = tmp / "chain.jsonl"
    print("S1 Genesis")
    L = AuditLedger(journal)
    chk("size >= 1", L.size() >= 1)
    g = L.get_entry(0)
    chk("genesis prev is zeros", g.previous_hash == "0" * 64)
    chk("hash format 64 hex", len(g.entry_hash) == 64)
    chk("verify ok", bool(L.verify()))

    print("S2 record()")
    eid1 = L.record("gate.emit", {"k": 1})
    eid2 = L.record("kernel.tick", {"n": 2})
    chk("entry_id is str", isinstance(eid1, str) and isinstance(eid2, str))
    chk("indices monotonic", L.get_entry(1).index == 1 and L.get_entry(2).index == 2)
    chk("chain link", L.get_entry(2).previous_hash == L.get_entry(1).entry_hash)
    eid3 = L.record("x", "scalar")
    chk("scalar auto-wrap", L.get_entry(3).payload.get("value") == "scalar")
    try:
        L.record("", {})
        chk("empty topic rejected", False)
    except ValueError:
        chk("empty topic rejected", True)

    print("S3 verify() intact")
    r = L.verify()
    chk("type", isinstance(r, VerificationResult))
    chk("ok True", r.ok is True)
    chk("bool true", bool(r) is True)
    chk("as_dict", r.as_dict()["ok"] is True)

    print("S4 Tamper detection")
    chain = list(L._chain)
    # mutate payload at index 1
    from dataclasses import replace
    bad = replace(chain[1], payload={"tampered": True})
    # recompute would not match stored hash — leave entry_hash stale
    corrupted = list(chain)
    corrupted[1] = bad
    r_tamper = _verify_chain(corrupted)
    chk("tamper detected", r_tamper.ok is False)
    chk("at least 1 break", len(r_tamper.breaks) >= 1)
    kinds = {b.kind for b in r_tamper.breaks}
    chk("hash_mismatch present", "hash_mismatch" in kinds)

    print("S5 HMAC seal")
    secret = b"test-secret-key-32bytes-long!!!!"
    js = tmp / "sealed.jsonl"
    S = AuditLedger(js, hmac_secret=secret)
    sid = S.record("sealed.event", {"a": 1})
    e = S.get_entry(S.size() - 1)
    chk("seal non-empty", len(e.author_seal) == 64)
    # secret must not appear in file
    text = js.read_text()
    chk("secret absent from JSONL", "test-secret" not in text)

    print("S6 epoch_snapshot()")
    before = L.size()
    snap_id = L.epoch_snapshot("daily-close")
    chk("snapshot id str", isinstance(snap_id, str))
    chk("size grew", L.size() == before + 1)
    snap = L.get_entry(L.size() - 1)
    chk("topic", snap.topic == "ledger.epoch_snapshot")
    chk("label stored", snap.payload.get("label") == "daily-close")
    chk("still valid", L.verify().ok)

    print("S7 public_log()")
    pub = L.public_log(limit=3)
    chk("limit slices", len(pub) == 3)
    chk("no raw payload key", all("payload" not in row for row in pub))
    chk("fingerprint present", all("payload_fingerprint" in row for row in pub))
    all_pub = L.public_log(limit=0)
    chk("limit 0 = full", len(all_pub) == L.size())

    print("S8 Gate hook")
    calls: list[tuple[str, str]] = []

    def mock_gate(topic: str, entry_id: str) -> None:
        calls.append((topic, entry_id))

    jh = tmp / "hook.jsonl"
    H = AuditLedger(jh, on_record=mock_gate)
    # genesis does not fire hook
    geid = H.record("gate.test", {"x": 1})
    chk("hook fired once for record", len(calls) >= 1)
    chk("hook topic", calls[0][0] == "gate.test")
    chk("hook entry_id", calls[0][1] == geid)
    H.epoch_snapshot("s")
    chk("hook fired for snapshot", len(calls) >= 2)

    def bad_hook(topic: str, entry_id: str) -> None:
        raise RuntimeError("boom")

    jb = tmp / "badhook.jsonl"
    B = AuditLedger(jb, on_record=bad_hook)
    B.record("still.works", {})
    chk("bad hook does not break chain", B.verify().ok)

    print("S9 JSONL persistence")
    jp = tmp / "persist.jsonl"
    P1 = AuditLedger(jp)
    P1.record("session.A", {"v": 1})
    P1.record("session.B", {"v": 2})
    size1 = P1.size()
    head1 = P1.head()
    P2 = AuditLedger(jp)
    chk("size survives restart", P2.size() == size1)
    chk("head survives restart", P2.head() == head1)
    P2.record("session.C", {"v": 3})
    P3 = AuditLedger(jp)
    chk("extension after reload", P3.size() == size1 + 1)
    chk("verify after reload", P3.verify().ok)

    # corrupt
    lines = jp.read_text().splitlines(True)
    if len(lines) > 2:
        lines[2] = lines[2].rstrip("\n") + "CORRUPTED\n"
        jp.write_text("".join(lines))
        try:
            AuditLedger(jp)
            chk("corrupt raises", False)
        except Exception:
            chk("corrupt raises", True)

    print("S10 Append-only surface")
    for name in ("update", "delete", "remove", "replace", "rewrite", "edit", "pop"):
        chk(f"no public {name}", not hasattr(AuditLedger, name) or not callable(getattr(AuditLedger, name, None)))

    print("S11 Thread safety")
    jt = tmp / "threads.jsonl"
    T = AuditLedger(jt)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(50):
                T.record(f"t.{n}", {"i": i})
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    chk("no thread exceptions", len(errors) == 0)
    # genesis + 8*50
    chk("final size", T.size() == 1 + 8 * 50)
    chk("verify after threads", T.verify().ok)

    print("S12 Boundaries")
    try:
        L.get_entry(99999)
        chk("OOB IndexError", False)
    except IndexError:
        chk("OOB IndexError", True)
    empty_path = tmp / "empty-dir"
    empty_path.mkdir(exist_ok=True)
    # fresh ledger always has genesis
    E = AuditLedger(tmp / "empty.jsonl")
    chk("empty-ish verifies", E.verify().ok)

    print("\nALL SECTIONS GREEN")


if __name__ == "__main__":
    main()
