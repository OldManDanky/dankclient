"""The installer actually installed, under wine, and upgraded over the last one.

    python3 tools/wine_check.py

`release_check.py` takes the .msi apart and reads its tables.  This runs it.
The difference matters: the tables say `RemoveExistingProducts` is sequenced
after `InstallFinalize`, but only an install says the interpreter is still
there afterwards -- and 0.2.0 shipped an upgrade that removed the Python it
had just installed over.  Every Windows fault so far was found by somebody
running Windows; this is the first of them a Linux box can catch on its own.

So: install the release before this one, install this one over the top, and
then ask of the folder that is left --

* is every file byte for byte what `build_windows.py` built?
* is `python\\pythonw.exe` still there?
* does `mud\\__init__.py` say the new version?
* did `RemoveExistingProducts` really end after `InstallFinalize`?
* is there one shortcut in the Start menu, not two?
* and does uninstalling leave nothing behind?

wine is not Windows.  A pass here is not a promise, and the answer to a
failure is to look at the log before believing it about the installer.  What
it is good for is the fault that leaves a folder visibly wrong.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from mud import NAME, SLUG, __version__  # noqa: E402

PREFIX = Path(os.environ.get("DANK_WINEPREFIX", Path.home() / "3kdev" / "wineprefix"))
INSIDE = ("drive_c/users/{user}/AppData/Local/Programs/{name}")
MENU = "drive_c/users/{user}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/{name}"
ENV = {
    "WINEPREFIX": str(PREFIX),
    "WINEARCH": "win64",
    "WINEDLLOVERRIDES": "mscoree,mshtml=",   # no mono, no gecko, no dialogs
    "WINEDEBUG": "-all",
    "DISPLAY": "",                            # /qn means nothing needs a screen
}


def wine(*args: str, timeout: int = 420) -> subprocess.CompletedProcess:
    return subprocess.run(["wine", *args], env={**os.environ, **ENV},
                          capture_output=True, text=True, timeout=timeout)


def where(pattern: str) -> Path:
    return PREFIX / pattern.format(user=os.environ.get("USER", "root"), name=NAME)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_of(name: str) -> tuple:
    got = re.search(rf"{re.escape(SLUG)}-(\d+(?:\.\d+)*)\.msi$", name)
    return tuple(int(n) for n in got.group(1).split(".")) if got else ()


def previous() -> Path | None:
    """The newest release in dist/ that is older than this one."""
    mine = version_of(f"{SLUG}-{__version__}.msi")
    older = sorted((version_of(p.name), p) for p in (HERE / "dist").glob(f"{SLUG}-*.msi")
                   if version_of(p.name) and version_of(p.name) < mine)
    return older[-1][1] if older else None


def log_order(log: Path) -> tuple[int, int]:
    """Where RemoveExistingProducts and InstallFinalize *ended*, in the log."""
    text = log.read_bytes().decode("utf-8", "replace").replace("\x00", "")
    at = {}
    for n, line in enumerate(text.splitlines()):
        got = re.match(r"Action ended [\d:]+ (\w+)\.", line)
        if got:
            at.setdefault(got.group(1), n)
    return at.get("RemoveExistingProducts", -1), at.get("InstallFinalize", -1)


def main() -> int:
    problems: list[str] = []
    msi = HERE / "dist" / f"{SLUG}-{__version__}.msi"
    built = HERE / "dist" / SLUG
    if not shutil.which("wine"):
        print("wine is not installed -- nothing to run")
        return 0
    if not msi.exists() or not built.is_dir():
        print(f"no {msi.name} and program folder to install -- build first")
        return 1
    old = previous()
    if old is None:
        print("no older release in dist/ -- upgrade cannot be tested, installing only")

    if not (PREFIX / "system.reg").exists():
        print(f"making a wine prefix in {PREFIX}")
        PREFIX.parent.mkdir(parents=True, exist_ok=True)
        wine("wineboot", "-i")

    folder, menu = where(INSIDE), where(MENU)
    # Start from nothing, whatever a previous run left.
    for path in filter(None, [msi, old]):
        wine("msiexec", "/x", str(path), "/qn")
    if folder.exists():
        problems.append(f"uninstalling did not remove {folder.name} -- files left behind")
        shutil.rmtree(folder, ignore_errors=True)

    if old is not None:
        got = wine("msiexec", "/i", str(old), "/qn")
        if got.returncode != 0 or not folder.is_dir():
            print(got.stdout[-2000:], got.stderr[-2000:])
            problems.append(f"{old.name} would not install under wine at all")
            print_problems(problems)
            return 1
        print(f"{old.name} installed: {sum(1 for p in folder.rglob('*') if p.is_file())} files")

    log = PREFIX / "install.log"
    log.unlink(missing_ok=True)
    got = wine("msiexec", "/i", str(msi), "/qn", "/L*v", str(log))
    if got.returncode != 0 or not folder.is_dir():
        print(got.stdout[-2000:], got.stderr[-2000:])
        problems.append(f"{msi.name} would not install under wine")
        print_problems(problems)
        return 1

    # What landed, against what was built.
    landed = {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file()}
    wanted = {p.relative_to(built).as_posix(): sha(p) for p in built.rglob("*") if p.is_file()}
    if landed != wanted:
        missing = sorted(set(wanted) - set(landed))[:5]
        extra = sorted(set(landed) - set(wanted))[:5]
        differ = sorted(k for k in set(landed) & set(wanted) if landed[k] != wanted[k])[:5]
        problems.append(f"what installed is not what was built "
                        f"(missing {missing}, left over {extra}, changed {differ})")
    else:
        print(f"{len(landed)} files installed, every SHA-256 matching the build")

    if not (folder / "python" / "pythonw.exe").exists():
        problems.append("no python\\pythonw.exe after the upgrade (0.2.0's bug)")
    said = (folder / "mud" / "__init__.py").read_text(encoding="utf-8", errors="replace")
    if f'"{__version__}"' not in said:
        problems.append(f"the installed client does not say it is {__version__}")
    if old is not None:
        removed, finalize = log_order(log)
        if removed < 0 or finalize < 0:
            problems.append("the log does not say both RemoveExistingProducts and "
                            "InstallFinalize ran")
        elif removed < finalize:
            problems.append("RemoveExistingProducts ran before InstallFinalize -- the old "
                            "version was taken out before the new one was in")
        else:
            print("RemoveExistingProducts ended after InstallFinalize, as it must")
    shortcuts = sorted(p.name for p in menu.glob("*.lnk")) if menu.is_dir() else []
    if len(shortcuts) != 1:
        problems.append(f"{len(shortcuts)} shortcuts in the Start menu, not one: {shortcuts}")
    else:
        print(f"one Start menu shortcut, {shortcuts[0]}")

    # And it goes away again.
    wine("msiexec", "/x", str(msi), "/qn")
    left = [p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()] \
        if folder.exists() else []
    if left:
        problems.append(f"uninstalling left {len(left)} files behind, e.g. {left[:5]}")
    elif menu.is_dir() and list(menu.glob("*.lnk")):
        problems.append("uninstalling left the Start menu shortcut behind")
    else:
        print("uninstalled, nothing left behind")

    print_problems(problems)
    return 1 if problems else 0


def print_problems(problems: list[str]) -> None:
    for p in problems:
        print(f"  PROBLEM  {p}")
    if not problems:
        print("installed, upgraded and uninstalled under wine with nothing wrong")


if __name__ == "__main__":
    sys.exit(main())
