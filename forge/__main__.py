"""
python -m forge  → boot kernel, print health, shutdown cleanly.
"""

from __future__ import annotations

import json
import logging
import signal
import sys

from forge.fabric.kernel import boot_forge

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)


def main() -> int:
    k = boot_forge()
    print(json.dumps(k.health(), indent=2, default=str))

    def _stop(signum, frame):
        print(json.dumps(k.shutdown(), indent=2, default=str))
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # One-shot demo boot: health then orderly shutdown
    print(json.dumps(k.shutdown(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
