"""
Forge Spine — fabric organs.

Public surface (growing):
  - Gate (forward-declared pathway registry)
  - Forge (privileged creator)
  - Capsule (hot-swap tool loader)
"""

from __future__ import annotations

__version__ = "0.2.0"

# Soft imports so the package can be imported even while organs are still landing.
try:
    from forge.fabric.forge import Forge, Role, PathwayDescriptor, SealedOrgan, VesselSpec
except ImportError:
    pass

try:
    from forge.fabric.capsule import CapsuleStore, Capsule
except ImportError:
    pass
