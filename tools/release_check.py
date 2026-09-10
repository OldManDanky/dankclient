"""Everything that has to be true before a release goes out, in one run.

    python3 tools/release_check.py            the lot, building the installer
    python3 tools/release_check.py --no-build without building

1. the test suite -- Python, and the browser code under Node when there is one
2. privacy -- no player's name and no NUL byte in anything to be published
3. regression -- every capture replayed; nothing placed right is placed wrong
4. the installer, built and then taken apart again: every file byte for byte
   what was built, the version, the upgrade code that must never change, and
   the old version removed only after the new one is in

Each has caught something real that the others could not.  The installer
checks are the ones that caught a release with no Python in it.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from mud import SLUG, __version__  # noqa: E402

PY = sys.executable


def run(label: str, cmd: list[str], results: list, quiet: bool = True) -> bool:
    print(f"\n=== {label}")
    got = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    lines = (got.stdout + got.stderr).rstrip().splitlines()
    shown = [l for l in lines if not l.startswith("ok    ")] if quiet else lines
    print("\n".join(shown[-40:]))
    results.append((label, got.returncode == 0))
    return got.returncode == 0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_installer(results: list) -> None:
    print("\n=== installer, taken apart")
    msi = HERE / "dist" / f"{SLUG}-{__version__}.msi"
    folder = HERE / "dist" / SLUG
    if not shutil.which("msiextract") or not shutil.which("msiinfo"):
        print("msitools is not installed -- cannot take the installer apart")
        results.append(("installer, taken apart", False))
        return
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["msiextract", "-C", tmp, str(msi)], capture_output=True, check=True)
        roots = list(Path(tmp).rglob(f"{SLUG}.cmd"))
        if not roots:
            problems.append(f"no {SLUG}.cmd inside the installer")
        else:
            inside = roots[0].parent
            a = {p.relative_to(inside).as_posix(): sha(p) for p in inside.rglob("*") if p.is_file()}
            b = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file()}
            if a != b:
                missing = sorted(set(b) - set(a))[:5]
                differ = sorted(k for k in set(a) & set(b) if a[k] != b[k])[:5]
                problems.append(f"contents differ from the build (missing {missing}, changed {differ})")
            else:
                print(f"{len(a)} files, every SHA-256 matching the build")
            if not (inside / "python" / "pythonw.exe").exists():
                problems.append("no python\\pythonw.exe inside")
    props = subprocess.run(["msiinfo", "export", str(msi), "Property"],
                           capture_output=True, text=True).stdout
    seq = subprocess.run(["msiinfo", "export", str(msi), "InstallExecuteSequence"],
                         capture_output=True, text=True).stdout
    actions = subprocess.run(["msiinfo", "export", str(msi), "CustomAction"],
                             capture_output=True, text=True).stdout
    want_code = re.search(r'UPGRADE_CODE\s*=\s*"([0-9A-F-]+)"',
                          (HERE / "tools" / "build_msi.py").read_text()).group(1)
    version = re.search(r"ProductVersion\t(\S+)", props)
    code = re.search(r"UpgradeCode\t\{?([0-9A-F-]+)\}?", props)
    order = {m.group(1): int(m.group(2)) for m in re.finditer(r"^(\w+)\t[^\t]*\t(\d+)", seq, re.M)}
    if not version or version.group(1) != __version__:
        problems.append(f"version is {version.group(1) if version else None}, not {__version__}")
    if not code or code.group(1) != want_code:
        problems.append("the upgrade code has changed -- Windows will install beside the old one")
    if order.get("RemoveExistingProducts", 0) <= order.get("InstallFinalize", 10 ** 6):
        problems.append("the old version is removed before the new one is in (0.2.0's bug)")
    if "SayWhere" not in actions:
        problems.append("the finish screen will not say where it installed")
    if problems:
        for p in problems:
            print(f"  PROBLEM  {p}")
    else:
        print(f"version {__version__}, upgrade code unchanged, old version removed after "
              "the new one is in, finish screen says where")
    results.append(("installer, taken apart", not problems))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-build", action="store_true", help="skip building the installer")
    args = ap.parse_args()
    results: list = []
    run("tests", [PY, "tests/run.py"], results)
    run("privacy", [PY, "tools/privacy.py"], results, quiet=False)
    run("regression (every capture replayed)", [PY, "tools/regress.py"], results, quiet=False)
    if not args.no_build:
        built = (run("icon", [PY, "tools/make_icon.py"], results)
                 and run("program folder", [PY, "tools/build_windows.py", "--zip"], results)
                 and run("build installer", [PY, "-W", "error::SyntaxWarning", "tools/build_msi.py"], results))
        if built:
            check_installer(results)

    print("\n=== summary")
    for label, ok in results:
        print(f"  {'pass' if ok else 'FAIL'}  {label}")
    failed = [label for label, ok in results if not ok]
    print("\nready to release" if not failed else f"\nNOT ready: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
