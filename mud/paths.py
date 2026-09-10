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
import time
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


def write_atomically(path, text: str, private: bool = False) -> None:
    """Replace a file whole, or leave it exactly as it was.

    write_text() truncates first and writes second, so a crash, a forced
    shutdown or a full disk in between leaves half a file -- and half a
    rules.json loads as no rules at all, which the next save then writes back
    over the half.  Fifty triggers became two bytes that way in a test.  So the
    new text goes into a file beside it, is flushed to the disk, and is then
    renamed over the old one, which is a single step on every filesystem this
    runs on.

    `private` creates it readable by you alone, where modes mean anything: the
    character list can hold a password.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    spare = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(spare, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                 0o600 if private else 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(10):
            try:
                os.replace(spare, path)
                break
            except PermissionError:
                # Windows refuses to rename over a file somebody else has
                # open, and a virus scanner reading the old one counts.  It
                # lets go in milliseconds.
                if attempt == 9:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            spare.unlink()
        except OSError:
            pass
        raise
    if private:
        try:
            os.chmod(path, 0o600)       # in case it already existed, wider
        except OSError:
            pass


def set_aside(path) -> Path | None:
    """Move a file that would not load out of the way, and say where to.

    A settings file that cannot be read used to be treated as empty, and the
    next save wrote the emptiness back over it: whatever was recoverable in
    it was gone for good.  Kept beside the original under another name, it is
    still there for somebody to look at, and a save can no longer touch it.
    """
    path = Path(path)
    kept = path.with_name(f"{path.name}.unreadable-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        os.replace(path, kept)
    except OSError:
        return None
    print(f"[client] {path.name} could not be read; kept it as {kept.name}",
          file=sys.stderr)
    return kept
