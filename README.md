# forge-spine

Single living core for The Forge: Gate · Forge · Capsule · Ledger · Isolation · Hopper · Kernel.

## Quick start (Pop!_OS / Linux)

```bash
git clone git@github.com:munnchue-gif/forge-spine.git
cd forge-spine
git pull origin main

# Ledger self-test (must end ALL SECTIONS GREEN)
PYTHONPATH=. python3 -m forge.fabric.validate_ledger

# Boot kernel once
PYTHONPATH=. python3 -m forge
```

Set secrets when leaving dev mode:

```bash
export FORGE_SECRET='your-long-random-secret'
export FORGE_LEDGER_PATH="$HOME/.forge/ledger.jsonl"
```

## Protocol

Read `START_HERE.md` before any change. Status lives in `STATUS.md`.

## Layout

```
forge/
  __main__.py          # python -m forge
  fabric/
    gate.py            # FabricGate v2
    forge.py           # privileged creator
    capsule.py         # expand/collapse tools
    hub.py             # external hubs
    ledger.py          # hash-chained audit
    isolation.py       # capability membrane
    hopper.py          # 6-phase ejection
    kernel.py          # boot wiring
    validate_ledger.py
prompts/               # next organ super-prompts
docs/                  # mythos + hardware
```
