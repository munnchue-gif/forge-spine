# Super-prompt: Isolation + Hopper

You are the Apex Systems Architect for Forge Spine.

Produce production Isolation membrane + 6-phase Hopper that:

1. Capability classes (NETWORK, FILESYSTEM, GPU, etc.) with levels NONE → FULL
2. Envelope that enforces grants
3. GateToken binding; hard revoke in Hopper Phase 3 via Gate.revoke_vessel
4. Strict phases: HALT → INSCRIBE → REVOKE_TOKENS → DECONSTRUCT → RETURN_RESOURCES → SWEEP_ARENA
5. Pristine arena invariant after sweep
6. Records terminal state to Ledger
7. Kernel-compatible interfaces

Use the Gate v2 already in forge/fabric/gate.py.
Deliver isolation.py + hopper.py (or combined) + validation checklist.
