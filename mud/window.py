"""A window of its own, rather than a tab in somebody's browser.

The interface is a web page because that is the only way to draw a terminal,
a map and a dozen panels without a toolkit -- but a tab among thirty other
tabs is not an application.  Chromium's app mode gives the page a window with
no address bar, no tabs and its own entry in the taskbar, which is what most
"desktop apps" of this shape actually are.

Edge ships with Windows 10 and 11, so on the machine this is packaged for
there is always one.  Where there is not, the ordinary browser is still a
perfectly good answer and is what happens instead.

The window is given a profile directory of its own.  Without one it joins the
browser the player already has open -- which means their extensions run
against it, their session is shared with it, and closing it does not close
anything, because the process was already running.  With one, it is a separate
program that can be waited on: when the window closes, the client stops.  That
is the difference between an app and a page.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

#: Tried in order.  Edge first on Windows because it is always there.
WINDOWS = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
)

ELSEWHERE = ("microsoft-edge", "google-chrome", "chromium", "chromium-browser",
             "brave-browser", "vivaldi")


def find() -> str | None:
    """A Chromium that can be told to be a window.  None if there is not one."""
    if sys.platform == "win32":
        for pattern in WINDOWS:
            path = Path(os.path.expandvars(pattern))
            if "%" not in str(path) and path.exists():
                return str(path)
        return None
    for name in ELSEWHERE:
        found = shutil.which(name)
        if found:
            return found
    return None


def flags(url: str, profile: Path, width: int = 1280, height: int = 820) -> list:
    return [
        f"--app={url}",
        # Its own profile, so it is its own process: the player's extensions
        # do not run against it and closing the window means something.
        f"--user-data-dir={profile}",
        f"--window-size={width},{height}",
        "--no-first-run",
        "--no-default-browser-check",
        # It is a local page on a port we opened; the browser has no business
        # phoning home about it.
        "--disable-background-networking",
        "--disable-sync",
    ]


async def open_window(url: str, profile: Path, note=None):
    """Start the window.  Returns the process, or None if there is no browser.

    Failing to open a window is never a reason not to run: the server is up
    and the address has been printed, so the worst case is that somebody opens
    it themselves.
    """
    said = note or (lambda _text: None)
    exe = find()
    if exe is None:
        said("no Edge or Chrome found -- open the address above in a browser")
        return None
    profile.mkdir(parents=True, exist_ok=True)
    try:
        return await asyncio.create_subprocess_exec(
            exe, *flags(url, profile),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
    except OSError as exc:
        said(f"could not open a window: {exc}")
        return None
