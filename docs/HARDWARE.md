# Hardware & Runtime Doctrine

## Target Machine
- MSI Vector i9 HX
- 96 GB RAM
- RTX 5080 16 GB VRAM
- zram available
- NPU present (separate leg)

## Doctrine

1. **GPU is primary** for any model larger than ~7B and for all heavy coding / generation tasks.
2. **zram + CPU** are offload only. Use them to keep the GPU free for the next large job.
3. **NPU** runs a small always-on observer model that is spliced into the Gate (read-only awareness, never KERNEL).
4. **Keychain / Hot-swap**
   - Models live as GGUF (or equivalent) files on fast storage.
   - A loader process can map them into VRAM on demand and unmap them when idle.
   - Multiple models can be registered; only one heavy model occupies the GPU at a time unless explicit multi-model is requested.
5. **Capsules**
   - Tools, agents, and temporary environments arrive as `.tar` or `.zip` capsules.
   - The Capsule organ expands them into a controlled directory or memory region, runs them, then collapses and optionally shreds the working copy.
   - The original capsule archive is never modified.

## Recommended Local Stack (2026)
- Inference: llama.cpp / llama-server or vLLM
- Quant: Q4_K_M or Q5_K_M for 16 GB
- Serving: localhost only, OpenAI-compatible endpoint
- Orchestration: n8n (self-hosted) + Forge pathways

## Unlocked Model Policy
- The unrestricted coder model runs on the GPU keychain.
- It is never given KERNEL or OVERSEER role.
- It can only call pathways that have been explicitly registered.
- This is how the system stays powerful without becoming uncontrollable.
