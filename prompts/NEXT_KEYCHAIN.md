# Super-prompt: GPU Keychain loader

You are the Apex Systems Architect for Forge Spine.

Implement forge/fabric/keychain.py — GPU-first model hot-swap loader.

Requirements:
1. Register models by name + path (GGUF or local runtime path)
2. load(name) prefers GPU; optional CPU/zram offload layers
3. unload(name) frees VRAM
4. Only one heavy model on GPU unless explicit multi allowed
5. Never grants KERNEL role to any model
6. Integrates with HubSocket (kind=model) and CapsuleStore where useful
7. Thread-safe registry; status() for Kernel health()
8. Hardware context: RTX 5080 16GB, 96GB RAM, zram available

Keep Kernel compatibility. Deliver complete keychain.py + short usage notes.
Do not invent new organs beyond Keychain.
