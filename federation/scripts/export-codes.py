#!/usr/bin/env python3
"""export-codes.py — Print unused access codes as a formatted list for distribution."""

import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "access-codes.json"


def main():
    if not DATA_PATH.exists():
        print("Error: data/access-codes.json not found", file=sys.stderr)
        sys.exit(1)

    codes = json.loads(DATA_PATH.read_text())
    unused = [c for c in codes if not c["usedAt"]]

    print(f"Unused Access Codes ({len(unused)}/{len(codes)} total)")
    print("=" * 40)
    for entry in unused:
        print(f"  {entry['code']}   (created: {entry['createdAt'][:10]})")
    print("=" * 40)
    print(f"Total unused: {len(unused)}")


if __name__ == "__main__":
    main()
