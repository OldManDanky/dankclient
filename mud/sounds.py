"""Sounds for things that happen: which one, and your own if you gave one.

Every event has three answers -- the client's built-in chime, nothing, or a
file you uploaded -- chosen under Options -> Sounds.  The files are kept here,
in the data folder beside the map, rather than in the browser: the window's
storage is per address, the address has a port in it, and the port is "8080
or the next free one", so a sound kept in the browser could vanish on the day
8080 was busy.  The page plays one from `/sounds/<event>`.

Only the events below, and only one file each, named after its event.  A
name the page sends is never a path.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from pathlib import Path

from .paths import set_aside, write_atomically

#: What can have a sound, and how Options says it.
SLOTS = {
    "tell": "A tell to you",
    "channel": "A channel line you chose to ding",
    "bell": "3K's bell (somebody used wake)",
    "bot": "A bot ends by itself",
    "idle": "You have been idle (the deadman trips)",
    "disconnect": "The MUD drops you",
}
CHOICES = ("builtin", "none", "file")
#: What a browser will play.  The browser decides whether it really can.
KINDS = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
         ".oga": "audio/ogg", ".m4a": "audio/mp4", ".aac": "audio/aac",
         ".webm": "audio/webm", ".flac": "audio/flac"}
#: Biggest file taken.  A sound for a tell is a second or two; two megabytes
#: is a long one, and the upload travels over the page's own socket.
MOST = 2 << 20


class Sounds:
    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder)
        self.path = self.folder / "sounds.json"
        self.chosen: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        self.chosen = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("not a set of sounds")
        except (ValueError, OSError):
            set_aside(self.path)
            return
        self.chosen = {k: v for k, v in raw.items()
                       if k in SLOTS and isinstance(v, dict)
                       and v.get("choice") in CHOICES}

    def _save(self) -> None:
        write_atomically(self.path, json.dumps(self.chosen, indent=2))

    def file(self, slot: str) -> Path | None:
        """The uploaded file for an event, if there is one."""
        if slot not in SLOTS:
            return None
        got = self.chosen.get(slot, {}).get("file", "")
        path = self.folder / got if got else None
        return path if path and path.name == got and path.is_file() else None

    def listing(self) -> list[dict]:
        """For the page: every event, what it plays, and your file's name."""
        out = []
        for slot, label in SLOTS.items():
            got = self.chosen.get(slot, {})
            path = self.file(slot)
            choice = got.get("choice", "builtin")
            if choice == "file" and path is None:
                choice = "builtin"                 # the file has gone
            out.append({"slot": slot, "label": label, "choice": choice,
                        "name": got.get("name", "") if path else "",
                        "stamp": path.stat().st_mtime_ns // 1000000 if path else 0})
        return out

    def choose(self, slot: str, choice: str) -> str | None:
        if slot not in SLOTS:
            return f"no such sound {slot!r}"
        if choice not in CHOICES:
            return f"no such choice {choice!r}"
        if choice == "file" and self.file(slot) is None:
            return "upload a file for it first"
        self.chosen.setdefault(slot, {})["choice"] = choice
        self._save()
        return None

    def upload(self, slot: str, name: str, data: str) -> str | None:
        """Keep a file for an event and play it from now on."""
        if slot not in SLOTS:
            return f"no such sound {slot!r}"
        # Only its own name, whichever way a path was written.
        name = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()[:120]
        ext = Path(name).suffix.lower()
        if ext not in KINDS:
            return (f"{name or 'that'} is not a sound file this can play -- "
                    + ", ".join(sorted(KINDS)))
        try:
            body = base64.b64decode(str(data or ""), validate=True)
        except (binascii.Error, ValueError):
            return "the file did not arrive whole"
        if not body:
            return "that file is empty"
        if len(body) > MOST:
            return f"that file is {len(body) / 1048576:.1f} MB; the most is {MOST >> 20} MB"
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / f"{slot}{ext}"
        spare = self.folder / f".{slot}{ext}.{os.getpid()}.tmp"
        spare.write_bytes(body)
        os.replace(spare, target)
        for other in KINDS:                    # the one it replaces, if another kind
            if other != ext:
                try:
                    (self.folder / f"{slot}{other}").unlink()
                except OSError:
                    pass
        self.chosen[slot] = {"choice": "file", "file": target.name, "name": name,
                             "at": time.strftime("%Y-%m-%d %H:%M")}
        self._save()
        return None

    def remove(self, slot: str) -> str | None:
        """Throw your file away and go back to the built-in sound."""
        if slot not in SLOTS:
            return f"no such sound {slot!r}"
        path = self.file(slot)
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass
        self.chosen[slot] = {"choice": "builtin"}
        self._save()
        return None
