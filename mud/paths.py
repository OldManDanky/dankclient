"""Where the client keeps its things.

Its own module because two very different callers need the answer: the command
line, which has to work it out before anything is opened, and the browser,
which has to be able to say it out loud.  "Where is my map" is a question that
gets asked more than once, and a client that cannot answer it is one you have
to go looking through a filesystem for.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import SLUG


def home() -> Path:
    """The directory this client keeps its things in.

    Everything used to be relative to the working directory, which is fine
    while the only way to run it is `python3 -m mud` from a checkout and wrong
    the moment it is installed: a command you can type anywhere would otherwise
    scatter a map, a profile directory and a pile of captures into whatever
    directory you happened to be standing in.

    An existing `map.sqlite` beside you wins, so a checkout that already has
    one keeps working exactly as it did.
    """
    if Path("map.sqlite").exists():
        return Path(".")
    said = os.environ.get("DANK_HOME") or os.environ.get("THREEK_HOME")
    if said:
        return Path(said).expanduser()
    if sys.platform == "win32":
        # Never beside the program.  An installer puts that in Program Files,
        # which the user it installed for cannot write to -- and the map, the
        # profiles and the captures are all things the client writes.
        base = Path(os.environ.get("LOCALAPPDATA") or "~/AppData/Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or "~/.local/share")
    base = base.expanduser()
    mine = base / SLUG
    # An installation that predates the name keeps its map: renaming the
    # application is not a reason for anybody to lose fifty thousand rooms.
    was = base / "3k"
    if not mine.exists() and (was / "map.sqlite").exists():
        return was
    return mine


def program() -> Path:
    """The folder the client itself was installed into."""
    return Path(__file__).resolve().parent.parent
