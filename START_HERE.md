# START HERE — Forge Spine Protocol

**Read this before any code, any model, any handoff.**

## Rules of Engagement

1. This repo is the **only** living spine. Do not scatter changes into old repos.
2. Every change must be small, verifiable, and committed with a clear message.
3. Models must identify themselves in commit messages or STATUS logs:
   ```
   AI NODE COMMIT LOG
   model: <name>
   account: <account>
   action: <what was done>
   files: <list>
   ```
4. Never invent new ways into the system. All privileged actions go through Gate pathways.
5. Capsules are preferred over permanent installs. Expand → use → collapse.
6. GPU is primary. CPU/zram are secondary offload only.
7. The Forge organ is SOVEREIGN. Only Kernel / Overseer roles may call it.

## Current Priority Order

1. Gate v2 — done
2. Forge organ — done
3. Capsule loader — done
4. Ledger v3 — done (validate green)
5. Isolation + Hopper — done
6. Kernel boot + `python -m forge` — done
7. Local unrestricted model serving (GPU keychain) — next
8. NPU light model splice

## Forbidden

- Soft protocol ("I'll just fix this one thing")
- Copying old broken files from previous repos without critique
- Giving models KERNEL role
- Permanent installs of tools that can be capsules

When in doubt: stop, read this file again, then act.
