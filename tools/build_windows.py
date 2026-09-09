#!/usr/bin/env python3
"""Build the Windows client: Python and the app in one folder.

A 3K player has no Python and should not have to get one.  The embeddable
distribution from python.org is a zip of exactly the interpreter -- no
installer, no registry, no PATH -- so the whole client becomes a folder you
copy, which is also what an MSI wants to lay down.

    python3 tools/build_windows.py            build into dist/3k
    python3 tools/build_windows.py --zip      ...and zip it for testing

This runs anywhere, Linux included: nothing is compiled and nothing is
executed, only unpacked and copied.  What it cannot do is *test* it, which
needs Windows.

Everything the client needs is in that distribution and was checked rather
than assumed: _sqlite3 for the map, _ssl for the update check, _socket for the
MUD, and pythonw.exe for a launch with no console behind it.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from mud import NAME, SLUG, __version__  # noqa: E402

#: Pinned, and checked.  A build that quietly picks up a different interpreter
#: is a build whose bugs cannot be reproduced.
PYTHON = "3.12.7"
EMBED = (f"https://www.python.org/ftp/python/{PYTHON}/"
         f"python-{PYTHON}-embed-amd64.zip")
EMBED_SHA = "0d57bb6cb078b74d23dbfe91f77d6780d45bed328911609f1f7ee2ba1606bf44"

#: The embeddable interpreter reads its whole sys.path from this file.  "."
#: is the interpreter's own folder; ".." is where the client lives.
PTH = f"python{PYTHON.replace('.', '')[:3]}.zip\n.\n..\n"

#: The one people run.  pythonw has no console at all, and --app puts the
#: interface in a window of its own rather than a tab in whatever browser
#: happens to be open.  Closing that window stops the client.
LAUNCHER = """@echo off
rem  Dank Mud Client.  Opens in a window of its own; closing it saves and quits.
start "" "%~dp0python\\pythonw.exe" -m mud --web --app --quiet %*
"""

#: ...and the one to run when it did not work.  A window that fails to appear
#: has nowhere to say why, so this keeps the console and holds it open.
SILENT = """@echo off
rem  The same thing with the console kept, for when something goes wrong: it
rem  is the only place that will say what.
setlocal
"%~dp0python\\python.exe" -m mud --web --app %*
echo.
pause
"""

READ_ME = """{name} {version}
{rule}

Run {slug}.cmd.  It opens in a window of its own.  Closing that window
saves your session and disconnects -- it does not send `quit`, so the
character is left exactly as a dropped connection would leave it.

Everything it keeps -- the map, your characters, your triggers and the session
logs -- goes in %LOCALAPPDATA%\\{slug}, not in this folder, so this folder
can be replaced wholesale by an update without touching any of it.

If nothing appears, run {slug}-console.cmd instead: it is the same thing
with the console kept open, and that is the only place a failure will say
what it was.

The window is drawn by Edge, which every Windows 10 and 11 machine has.  It
runs in a profile of its own, so your browser, your extensions and your logins
have nothing to do with it.

This client is free software under the GNU General Public License v3; see
LICENSE.  It includes xterm.js, which is under the MIT licence -- see
mud/ui/vendor/LICENSE-xterm.
"""


def fetch(cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    got = cache / f"python-{PYTHON}-embed-amd64.zip"
    if not got.exists():
        print(f"  downloading {EMBED}")
        with urllib.request.urlopen(EMBED, timeout=120) as reply:
            got.write_bytes(reply.read())
    digest = hashlib.sha256(got.read_bytes()).hexdigest()
    if digest != EMBED_SHA:
        raise SystemExit(
            f"the interpreter does not match what this build was written for\n"
            f"  expected {EMBED_SHA}\n  got      {digest}")
    print(f"  interpreter {PYTHON} verified")
    return got


def copy_package(into: Path) -> int:
    """The client itself, minus anything that is not the client."""
    files = 0
    for path in sorted((HERE / "mud").rglob("*")):
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        target = into / path.relative_to(HERE)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files += 1
    return files


def build(out: Path, cache: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    with zipfile.ZipFile(fetch(cache)) as zf:
        zf.extractall(out / "python")
    # The interpreter's path file decides what it can import.  Without ".."
    # added, `-m mud` in the folder above is invisible to it.
    for stale in (out / "python").glob("*._pth"):
        stale.write_text(PTH)

    files = copy_package(out)
    (out / f"{SLUG}.cmd").write_text(LAUNCHER, newline="\r\n")
    (out / f"{SLUG}-console.cmd").write_text(SILENT, newline="\r\n")
    (out / "README.txt").write_text(
        READ_ME.format(name=NAME, version=__version__, slug=SLUG,
                       rule="=" * (len(NAME) + len(__version__) + 1)),
        newline="\r\n")
    for name in ("LICENSE", "README.md"):
        if (HERE / name).exists():
            shutil.copy2(HERE / name, out / name)

    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"  {files} client files, {size // 1048576} MB in {out}")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(HERE / "dist" / SLUG))
    ap.add_argument("--cache", default=str(HERE / "dist" / "cache"),
                    help="where the interpreter download is kept")
    ap.add_argument("--zip", action="store_true",
                    help="also produce a zip, for carrying it to a Windows box")
    args = ap.parse_args(argv[1:])

    print(f"building {NAME} {__version__} for Windows")
    out = build(Path(args.out), Path(args.cache))
    if args.zip:
        # Anything that imported the client between the build and here has left
        # .pyc files behind, and those carry the absolute path they were
        # compiled from.  Nobody's home directory ships in a zip.
        swept = 0
        for stale in list(out.rglob("__pycache__")):
            shutil.rmtree(stale, ignore_errors=True)
            swept += 1
        if swept:
            print(f"  swept {swept} __pycache__ director{'y' if swept == 1 else 'ies'}")
        where = shutil.make_archive(
            str(out.parent / f"{SLUG}-{__version__}-windows"), "zip",
            root_dir=out.parent, base_dir=out.name)
        print(f"  {where} ({Path(where).stat().st_size // 1048576} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
