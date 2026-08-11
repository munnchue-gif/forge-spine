# Super-prompt: Ledger v2

You are the Apex Systems Architect for Forge Spine.

Produce a production-grade hash-chained AuditLedger that:

1. Append-only JSONL (or equivalent) with fsync
2. Each entry carries structural SHA-256 + optional HMAC author_seal
3. previous_hash links form a continuous chain
4. epoch_snapshot() creates first-class checkpoint entries
5. verify() recomputes the full chain and returns a clear result
6. public_log() returns AI-safe view (payload_fingerprint only, no secrets)
7. Thread-safe (RLock)
8. Compatible with Gate emit hooks (topic + payload)

Keep the interface minimal and Kernel-friendly:
  record(topic, payload) -> entry_id
  verify() -> VerificationResult
  epoch_snapshot(label) -> snapshot_id
  public_log(limit=N) -> list[dict]
  size() / head()

Deliver complete ledger.py + a short validate_ledger.py checklist.
Do not invent new organs. Stay inside the spine design.
