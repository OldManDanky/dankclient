#!/usr/bin/env python3
"""Minimal test runner -- stdlib only, so the project stays install-free."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


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

    ui_passed, ui_failed = ui_tests()
    passed, failed = passed + ui_passed, failed + ui_failed

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


def ui_tests() -> tuple[int, int]:
    """The browser code, run for real under Node when there is a Node.

    Every script is parsed, and each tests/ui/*.test.js loads the real file
    against a stand-in page and drives it.  Node is optional -- the project
    still takes no dependencies -- so without one this says so and the Python
    suite above stands on its own.
    """
    node = shutil.which("node")
    if node is None:
        print("\nUI tests skipped: no Node on this machine "
              "(the Python tests above still ran)")
        return 0, 0
    passed = failed = 0
    for js in sorted((ROOT / "mud" / "ui").glob("*.js")):
        got = subprocess.run([node, "--check", str(js)],
                             capture_output=True, text=True)
        if got.returncode:
            failed += 1
            print(f"FAIL  ui.syntax.{js.name}\n{got.stderr.strip()}\n")
        else:
            passed += 1
            print(f"ok    ui.syntax.{js.name}")
    for test in sorted((HERE / "ui").glob("*.test.js")):
        got = subprocess.run([node, str(test)], capture_output=True,
                             text=True, cwd=ROOT, timeout=120)
        seen = 0
        for line in got.stdout.splitlines():
            if line.startswith("PASS"):
                passed += 1
                seen += 1
                print(f"ok    ui.{test.stem}: {line[6:]}")
            elif line.startswith("FAIL"):
                failed += 1
                seen += 1
                print(f"FAIL  ui.{test.stem}: {line[6:]}")
        if got.returncode and not any(l.startswith("FAIL")
                                      for l in got.stdout.splitlines()):
            failed += 1
            print(f"FAIL  ui.{test.stem} crashed after {seen} checks:\n"
                  f"{got.stderr.strip()[-2000:]}\n")
    return passed, failed


if __name__ == "__main__":
    sys.exit(main())
