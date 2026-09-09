#!/usr/bin/env python3
"""Minimal test runner -- stdlib only, so the project stays install-free."""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    passed = failed = 0
    for path in sorted(HERE.glob("test_*.py")):
        mod = load(path)
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            fn = getattr(mod, name)
            if not callable(fn):
                continue
            try:
                fn()
            except Exception:
                failed += 1
                print(f"FAIL  {path.stem}.{name}")
                print(traceback.format_exc(limit=3, chain=False).rstrip())
                print()
            else:
                passed += 1
                print(f"ok    {path.stem}.{name}")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
