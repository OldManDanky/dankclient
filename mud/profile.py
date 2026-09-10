"""Characters, and which of your settings belong to one rather than to you.

A player has several characters and they are not the same person.  One
character's aliases are muscle memory for that character's guild; on another,
half of them are commands that do not exist.  So the four kinds of rule --
triggers, aliases, events, stat watches -- and the line markers follow the
character.

Two things deliberately do not.  The map is geography: a road is in the same
place whoever walks it, and splitting fifty thousand rooms per character would
mean walking them again for nothing.  Routes are paths across that map, so
they go with it.

Each character gets a directory of its own::

    profiles/characters.json     the list, and any passwords you asked us to keep
    profiles/player/rules.json  triggers, aliases, events, watches
    profiles/player/prefixes.json

The list is written 0600 where that means anything, because it may hold a
password.  That is a real choice with a real cost and the screen that offers it
says so: a password kept here is in plain text on this machine, and anything
that can read your home directory can read it.

On Windows there are no modes -- os.open ignores them and chmod only moves the
read-only bit -- so the protection there is the directory instead: the client
keeps its files under %LOCALAPPDATA%, which is already the user's own.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import set_aside, write_atomically
from .session import DEFAULT_HOST, DEFAULT_PORT

#: Where the characters live, unless you say otherwise.
DEFAULT_ROOT = "profiles"

#: Settings that predate profiles get copied into the first character that
#: asks for them, rather than being left behind in a directory nobody reads.
SEED_FROM = "scripts"


@dataclass
class Character:
    name: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    #: kept only if you asked; never sent back to the browser
    password: str = ""
    note: str = ""
    last_played: float = 0.0

    @property
    def slug(self) -> str:
        """A directory name that is recognisably the character's."""
        clean = re.sub(r"[^a-z0-9]+", "-", self.name.strip().lower()).strip("-")
        return clean or "character"

    def public(self) -> dict:
        """Everything about this character except the one secret bit."""
        out = asdict(self)
        out.pop("password")
        out["has_password"] = bool(self.password)
        out["slug"] = self.slug
        return out


@dataclass
class Characters:
    root: Path = field(default_factory=lambda: Path(DEFAULT_ROOT))
    seed_from: Path = field(default_factory=lambda: Path(SEED_FROM))
    all: list[Character] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.seed_from = Path(self.seed_from)
        self.load()

    # --- the list -----------------------------------------------------------

    @property
    def path(self) -> Path:
        return self.root / "characters.json"

    def load(self) -> None:
        if not self.path.exists():
            self.all = []
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, list):
                raise ValueError("not a list of characters")
        except (ValueError, OSError):
            set_aside(self.path)         # kept, not overwritten by the next save
            self.all = []
            return
        fields = {f for f in Character.__dataclass_fields__}
        self.all = [Character(**{k: v for k, v in c.items() if k in fields})
                    for c in raw
                    if isinstance(c, dict) and isinstance(c.get("name"), str)
                    and c["name"].strip()]

    def save(self) -> None:
        # Created closed rather than written open and narrowed afterwards, and
        # written whole or not at all.  Windows ignores the mode; there the
        # parent directory is the guard.
        write_atomically(self.path,
                         json.dumps([asdict(c) for c in self.all], indent=2),
                         private=True)

    def public(self) -> list[dict]:
        return [c.public() for c in self.all]

    # --- one of them --------------------------------------------------------

    def get(self, name: str) -> Character | None:
        want = (name or "").strip().lower()
        return next((c for c in self.all if c.name.lower() == want), None)

    def put(self, char: Character) -> Character:
        """Add, or replace the one with the same name."""
        old = self.get(char.name)
        if old is None:
            self.all.append(char)
        else:
            # An empty password means "leave it alone", not "forget it": the
            # browser is never sent one back, so it cannot send one on.
            char.password = char.password or old.password
            self.all[self.all.index(old)] = char
        self.save()
        return char

    def forget(self, name: str) -> bool:
        char = self.get(name)
        if char is None:
            return False
        self.all.remove(char)
        self.save()
        return True

    def played(self, name: str) -> None:
        char = self.get(name)
        if char is not None:
            char.last_played = time.time()
            self.save()

    # --- where a character's own settings live ------------------------------

    def dir(self, name: str) -> Path:
        char = self.get(name) or Character(name)
        where = self.root / char.slug
        where.mkdir(parents=True, exist_ok=True)
        return where

    def rules_path(self, name: str) -> Path:
        return self._own(name, "rules.json")

    def prefixes_path(self, name: str) -> Path:
        return self._own(name, "prefixes.json")

    def _own(self, name: str, leaf: str) -> Path:
        """A character's copy of `leaf`, seeded from the shared one once.

        Somebody who has been using this client already has rules; the first
        character they make should start with them rather than with nothing.
        Copied, not moved: the second character starts from the same place,
        and neither can surprise the other afterwards.
        """
        mine = self.dir(name) / leaf
        shared = self.seed_from / leaf
        if not mine.exists() and shared.exists():
            try:
                shutil.copyfile(shared, mine)
            except OSError:
                pass
        return mine


def activate(char: Character, chars: Characters, session, scripts=None) -> None:
    """Point everything that belongs to a character at this one.

    One function because the pieces have to move together: rules that outlive
    a profile switch are rules firing on the wrong character, and that is the
    kind of thing you notice by watching yourself cast a spell you do not have.
    """
    session.character = char
    chars.played(char.name)
    # The client is up and logging before anybody has picked a character, so
    # this is the first moment the session row can say whose it is.
    if getattr(session, "logbook", None) is not None:
        session.logbook.played_by(char.name)
    session.reload_prefixes(chars.prefixes_path(char.name))
    rules = getattr(scripts, "rules", None)
    if rules is not None:
        rules.path = chars.rules_path(char.name)
        rules.load()
        rules.register()
