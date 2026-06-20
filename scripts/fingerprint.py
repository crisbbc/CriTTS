#!/usr/bin/env python3
"""Compute a content hash of requirements.txt and compare to stored marker.

Usage:
    python scripts/fingerprint.py           # print current hash
    python scripts/fingerprint.py --write   # write hash to .dep-hash
    python scripts/fingerprint.py --check   # exit 0 if match, 1 if mismatch
"""

import hashlib
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
REQ_PATH = SCRIPT_DIR / "requirements.txt"
MARKER_PATH = SCRIPT_DIR / ".dep-hash"


def compute_hash() -> str:
    """Return SHA-256 hex digest of requirements.txt content."""
    if not REQ_PATH.exists():
        print("requirements.txt not found", file=sys.stderr)
        sys.exit(2)
    return hashlib.sha256(REQ_PATH.read_bytes()).hexdigest()


def main() -> None:
    current = compute_hash()

    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        MARKER_PATH.write_text(current + "\n")
        print(f"Hash written: {current[:12]}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--check":
        if MARKER_PATH.exists() and MARKER_PATH.read_text().strip() == current:
            print("match")
            sys.exit(0)
        else:
            print("mismatch")
            sys.exit(1)
    else:
        print(current)


if __name__ == "__main__":
    main()
