"""
Forge Spine — Capsule organ.

Tools and temporary environments arrive as sealed .tar / .zip archives.
They are expanded into a controlled workspace when needed, used, then
collapsed. The original archive is never modified. This is the opposite
of permanent installation.

Design goals:
  - No permanent pollution of the host
  - Fast expand / collapse
  - Hash integrity of every capsule
  - Works with GPU offload patterns (capsule can contain model weights
    or tool code that is only mapped while active)
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import zipfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager


@dataclass(frozen=True, slots=True)
class Capsule:
    name: str
    archive_path: Path
    sha256: str
    format: str          # "tar" | "zip"
    registered_at: float
    metadata: dict = field(default_factory=dict)


class CapsuleError(Exception):
    pass


class CapsuleStore:
    """
    Registry + expander for capsules.

    Typical flow:
      store.register("/path/to/tool.tar.gz")
      with store.expand("tool-name") as workspace:
          # run the tool inside workspace
      # workspace is automatically cleaned
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root else Path(tempfile.gettempdir()) / "forge-capsules"
        self._root.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, Capsule] = {}

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def register(self, archive: Path | str, *, name: str | None = None, metadata: dict | None = None) -> Capsule:
        path = Path(archive).resolve()
        if not path.is_file():
            raise CapsuleError(f"Archive not found: {path}")

        suffix = path.suffix.lower()
        if suffix in {".tar", ".gz", ".tgz", ".bz2", ".xz"} or path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            fmt = "tar"
        elif suffix == ".zip":
            fmt = "zip"
        else:
            raise CapsuleError(f"Unsupported archive format: {path.name}")

        digest = self._hash_file(path)
        cap_name = name or path.stem.split(".")[0]

        capsule = Capsule(
            name=cap_name,
            archive_path=path,
            sha256=digest,
            format=fmt,
            registered_at=time.time(),
            metadata=metadata or {},
        )
        self._registry[cap_name] = capsule
        return capsule

    def get(self, name: str) -> Capsule:
        if name not in self._registry:
            raise CapsuleError(f"Capsule not registered: {name}")
        return self._registry[name]

    def list(self) -> tuple[Capsule, ...]:
        return tuple(self._registry.values())

    @contextmanager
    def expand(self, name: str) -> Iterator[Path]:
        """
        Expand the capsule into a temporary workspace.
        Yields the workspace Path. Automatically cleans on exit.
        """
        capsule = self.get(name)
        workspace = self._root / f"{name}-{capsule.sha256[:12]}"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)

        try:
            if capsule.format == "tar":
                with tarfile.open(capsule.archive_path, "r:*") as tar:
                    tar.extractall(workspace)
            else:
                with zipfile.ZipFile(capsule.archive_path, "r") as zf:
                    zf.extractall(workspace)
            yield workspace
        finally:
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

    def verify(self, name: str) -> bool:
        """Re-hash the archive and compare to the registered digest."""
        capsule = self.get(name)
        return self._hash_file(capsule.archive_path) == capsule.sha256
