"""The character settings that make 3K's output machine-readable.

3K lets a player wrap each kind of line in a prefix and suffix of their
choosing.  That is a preference, not a mudlib change, and it turns the text
stream from prose into delimited fields::

    -R-_Pinnacle Theatre Side Entrance (guild,n,chaos,...)-R-_
    -D-_A boring room.  Perhaps you should decorate it.-D-_
    -X-_    There are twelve obvious exits: guild, north, ...-X-_
    -i-A Trashcan.        -M-_Cur, the tradesman's dog.

Which matters because MIP does not carry everything.  It has no room id and no
description, so identifying a room from a standing start means reading the
text -- and reading a field with two ends is a different proposition from
guessing where prose stops.  With these set, a room is identifiable roughly
twice as often (68.6% against 33.5% on an imported map).

``room_long`` is the one worth having and the one usually left blank: it is
the description, and without it the other two thirds are unreachable.

The values are ours; the command that applies them is 3K's, so it lives in a
file you can edit rather than being compiled in::

    aset room_long_pref -D-_
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: variable -> marker.  Both ends of a field get the same marker, so it can be
#: found without knowing where it ends -- which is what a suffix is for and
#: why the room fields set both.
DEFAULTS: list[tuple[str, str]] = [
    ("room_short_pref", "-R-_"),
    ("room_short_suff", "-R-_"),
    ("room_long_pref", "-D-_"),
    ("room_long_suff", "-D-_"),
    ("room_exits_pref", "-X-_"),
    ("room_exits_suff", "-X-_"),
]

#: Sent after the settings, not as settings.
#:
#: The look_* markers are deliberately absent above.  3K appears to treat
#: them and the HAA records as two ways of doing one job: setting them stopped
#: HAA arriving at all, across every capture after the button was first
#: pressed.  3kdb sends "3klient HAA off" on purpose, because it wants the
#: text form -- we want the opposite.  HAA is what tells a route the command
#: the MUD accepts for a creature, and what fills the room panel's buttons,
#: and a marker on a line we were not reading is no trade for that.
#: The markers this client set on its first pass are cleared again, because
#: it set them: "aset <name> reset" is the form 3K takes.  Nothing else on the
#: character is touched -- these seven are the ones we asked for.
AFTER: list[str] = [
    "aset look_monster_pref reset",
    "aset look_player_pref reset",
    "aset look_weapon_pref reset",
    "aset look_armor_pref reset",
    "aset look_armour_pref reset",
    "aset look_object_pref reset",
    "aset look_other_pref reset",
    "3klient HAA on",
]

#: How 3K is asked to set one -- confirmed against the game, not inferred.
#: Still data rather than a constant in the code: it belongs to 3K, and the
#: day it changes should cost one line in a file, not a release.
VERB = "aset"


class Prefixes:
    def __init__(self, path: str | Path = "scripts/prefixes.json") -> None:
        self.path = Path(path)
        self.verb = VERB
        self.pairs = list(DEFAULTS)
        self.after = list(AFTER)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("not a settings object")
        except (ValueError, OSError):
            # The defaults stand, and the file is kept rather than saved over.
            from .paths import set_aside
            set_aside(self.path)
            return
        self.verb = str(raw.get("verb", VERB))
        pairs = raw.get("set")
        if isinstance(pairs, list):
            self.pairs = [(str(k), str(v)) for k, v in pairs
                          if isinstance(k, str)]
        after = raw.get("after")
        if isinstance(after, list):
            self.after = [str(c) for c in after]

    def save(self) -> None:
        from .paths import write_atomically
        write_atomically(self.path, json.dumps(
            {"verb": self.verb, "set": [list(p) for p in self.pairs],
             "after": self.after}, indent=2))

    def commands(self) -> list[str]:
        return ([f"{self.verb} {name} {value}" for name, value in self.pairs]
                + list(self.after))


class Hidden:
    """Takes the markers back out again, on the way to the screen.

    They exist to be read by a machine, and a machine has read them by the
    time anything is displayed.  Leaving them in means a player who types
    ``look`` sees the scaffolding::

        -R-_North of Center (e,w,s,n)                              -R-_   O-O-@
        -D-_The cobbles give way to a weird, twisting tile ...
        -D-_
        -X-_    There are four obvious exits: east, west, south, north     -X-_

    Three details make this more than a search and replace.

    A marker can straddle a read -- the stream arrives in whatever lengths the
    network hands over, not in lines -- so a tail that could still turn out to
    be one is held back rather than printed.  Held text is never more than a
    marker's worth, and a prompt flushes it, so nothing waits on the network
    to be seen.

    ``room_long``'s closing marker sits alone on its line.  Removing just the
    text would leave the blank line behind, so a marker that is the whole line
    takes the line with it.

    And 3K answers each setting by quoting it back::

        Variable room_short_pref set to: -R-_

    which is the one line where the marker is the message.  Blanking it there
    reads as the setting having failed, at the exact moment somebody is
    watching to see whether it worked -- so a line that names one of the
    variables keeps its markers.
    """

    def __init__(self, markers, keep=()) -> None:
        # Longest first: a marker that begins with another must go first, or
        # the shorter one eats its head and leaves the tail on screen.
        self.markers = sorted({m for m in markers if m}, key=len, reverse=True)
        self.keep = sorted({k for k in keep if k})
        self._raw = [m.encode("latin-1", "replace") for m in self.markers]
        self._keep = [k.encode("latin-1", "replace") for k in self.keep]
        self._longest = max((len(m) for m in self._raw), default=0)
        group = b"|".join(re.escape(m) for m in self._raw)
        #: a whole marker at the start of a line, still waiting to find out
        #: whether a newline follows.  The carriage return of a CRLF often
        #: arrives on its own, ahead of the newline that would settle it, so
        #: it counts as still waiting.
        self._maybe = re.compile(b"(?:" + group + b")[ \t]*\r?$") if group else None
        self._held = b""
        self._bol = True
        #: the line being printed named one of the variables, so its markers
        #: stand even though it arrived in pieces -- and the pieces so far, to
        #: notice a name that arrived split down the middle
        self._kept = False
        self._line = b""

    def line(self, text: str) -> str:
        """One whole line, markers removed.  Empty if it was only a marker."""
        if not any(m in text for m in self.markers):
            return text
        if any(k in text for k in self.keep):
            return text
        for m in self.markers:
            text = text.replace(m, "")
        return "" if not text.strip() else text

    def feed(self, chunk: bytes) -> bytes:
        """A chunk of the byte stream, markers removed."""
        if not self._raw:
            return chunk
        buf, self._held = self._held + chunk, b""
        head, sep, tail = buf.rpartition(b"\n")

        out = b""
        if sep:
            # Split on newlines alone.  splitlines() would also break on a
            # bare carriage return and on half a dozen control codes, and
            # 3K's output carries both.
            out = b"".join(self._one(line + b"\n")
                           for line in (head + sep).split(b"\n")[:-1])

        keep = self._dangling(tail, self._bol)
        if keep:
            self._held, tail = tail[-keep:], tail[:-keep]
        return out + self._part(tail)

    def flush(self) -> bytes:
        """Give up on a held tail -- at a prompt, nothing more is coming."""
        held, self._held = self._held, b""
        return held

    def _one(self, piece: bytes) -> bytes:
        """A complete line, ending whatever was already part-way printed."""
        started, self._line = self._bol, (self._line + piece)[-512:]
        body = piece.rstrip(b"\r\n")
        cut = piece if self._exempt() else self._plain(body)
        if cut is piece or cut == body:
            shown = piece                 # nothing of ours on this line
        elif started and not cut.strip():
            # A marker that was the whole line takes the line with it -- but
            # only if it was the whole line, and not the tail of one already
            # on screen, and only if a marker is why it is empty.  A blank
            # line the MUD sent is a blank line.
            shown = b""
        else:
            shown = cut + piece[len(body):]
        self._bol, self._kept, self._line = True, False, b""
        return shown

    def _part(self, tail: bytes) -> bytes:
        """The unfinished line at the end of a chunk -- usually the prompt."""
        if not tail:
            return b""
        self._line = (self._line + tail)[-512:]
        shown = tail if self._exempt() else self._plain(tail)
        if shown:
            self._bol = False
        return shown

    def _exempt(self) -> bool:
        """Is the line being printed one 3K is quoting a setting back on?

        Asked of the line so far rather than of the chunk: the name arrives
        before the marker it is quoting, but not always in the same read.
        """
        if not self._kept and any(k in self._line for k in self._keep):
            self._kept = True
        return self._kept

    def _dangling(self, tail: bytes, at_bol) -> int:
        """How much of `tail` might still grow into a marker."""
        if at_bol and self._maybe is not None and self._maybe.match(tail):
            return len(tail)              # a whole marker, awaiting its newline
        for n in range(min(self._longest - 1, len(tail)), 0, -1):
            part = tail[-n:]
            if any(m.startswith(part) and len(m) > n for m in self._raw):
                return n
        return 0

    def _plain(self, text: bytes) -> bytes:
        for m in self._raw:
            text = text.replace(m, b"")
        return text
