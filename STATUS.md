# Forge Spine — STATUS

**Updated:** 2026-08-12

## Locked (do not drift)

- [x] Repo created: `forge-spine` (private, single source of truth)
- [x] START_HERE.md protocol
- [x] Mythos + Hardware doctrine
- [x] Forge organ (privileged creator)
- [x] Capsule organ (expand/collapse tools)
- [x] Gate v2 (forward-declared pathway registry + three-axis)
- [x] Hub socket (external tool/repo hubs, capsule-friendly)
- [x] Ledger v3 (hash-chained JSONL, epoch snapshots, public_log, validate green)
- [x] Kernel (Ledger first → Gate emit → Forge → Capsule → Hub)
- [x] Isolation membrane (capability grants + vessel states)
- [x] Hopper (6-phase ejection + Gate.revoke_vessel + ledger)
- [x] `python -m forge` boot entry

## Next (in order)

1. GPU keychain model loader skeleton (`keychain.py`)
2. Optional: adopt evaluate-style FabricGate 2.0.0 (roles ∩, TokenMinter) — keep sign/authorize compatibility for Forge
3. NPU light observer splice into Gate
4. Minimal HTTP health endpoint (localhost only)
5. n8n pathway registration via Hub + Capsule
6. Glass UI stays separate (docs/ or other repo)

## Validate on machine

```bash
cd ~/forge-spine
git pull origin main
PYTHONPATH=. python3 -m forge.fabric.validate_ledger
PYTHONPATH=. python3 -m forge
```

## Old repos disposition

| Repo | Disposition | Useful keep |
|------|-------------|-------------|
| the-forge | Freeze / archive later | Kernel boot pattern, sandbox ideas |
| forge-os-core | Notes only | STATUS discipline, NPU context |
| fabric-core | Merge concepts then archive | Lightweight runtime ideas |
| fabric-ui / the-forge-ui | Glass only — keep separate | Visualization |
| forge-copilot | Keep for prompts/handoffs | PRE_PROMPT / MASTER_PROMPT |
| sovereign-forge-v4 / forge-arena | Archive when spine stable | Conceptual only |

Nothing is deleted yet. Useful ideas are pulled into spine; junk stays out.
