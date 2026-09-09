"""Reading the fields 3K wraps its output in, when a character asks it to.

MIP carries no room id and no description, so identifying a room from a
standing start means reading text.  A player can have 3K wrap each kind of
line in markers of their choosing, which turns that from guessing where prose
stops into reading a delimited field::

    -R-_A Vortex (e,w,s,enter)          -R-_    1-E-O-^-O
    -D-_The immediate area is extremely blurry ...
    ... a road leads out of the vortex to the south.
    -D-_

The markers are not guessed: the client is what sets them, so it knows what it
asked for.  They are still checked rather than trusted -- a room title only
counts when the exits in its brackets match the ones MIP sends -- because a
character may have been set up by hand years ago, or by somebody else.

Why it is worth the trouble: the room title arrives with every room and
arrives at once, where ``BAD`` names fewer than half of them and does it on
the two-second tick.  Getting your bearings in a fifty-thousand room map is
the difference between the first room and the third.
"""

from __future__ import annotations

from collections import deque

from .codes import parse_bad


class Markup:
    """Pulls the room title and description out of the text stream."""

    def __init__(self, room: str = "-R-_", desc: str = "-D-_") -> None:
        self.room, self.desc = room, desc
        #: Titles waiting for the room blocks they belong to.  A queue rather
        #: than a slot: text arrives before the MIP block it describes, but a
        #: block does not settle until the message *after* it, so by then the
        #: next room's title can already have been printed.  Matching on exits
        #: picks the right one out.
        self._pending: deque[dict] = deque(maxlen=4)
        self._collecting: list[str] | None = None

    @property
    def name(self) -> str:
        return self._pending[-1]["name"] if self._pending else ""

    @property
    def exits(self) -> list[str]:
        return self._pending[-1]["exits"] if self._pending else []

    @property
    def description(self) -> str:
        return self._pending[-1]["desc"] if self._pending else ""

    @classmethod
    def from_prefixes(cls, prefixes) -> "Markup":
        pairs = dict(getattr(prefixes, "pairs", ()))
        return cls(pairs.get("room_short_pref", "-R-_"),
                   pairs.get("room_long_pref", "-D-_"))

    def feed(self, line: str) -> None:
        """Take one line of plain text, ANSI already stripped."""
        if self._collecting is not None:
            if line.strip() == self.desc:
                if self._pending:
                    self._pending[-1]["desc"] = " ".join(self._collecting)
                self._collecting = None
            else:
                self._collecting.append(line.strip())
            return

        if self.room and line.startswith(self.room):
            # The suffix is the same marker, and 3K's own ASCII map follows it
            # on the same line, so cut at the second one.
            rest = line[len(self.room):]
            end = rest.find(self.room)
            name, exits = parse_bad((rest[:end] if end >= 0 else rest).strip())
            self._pending.append({"name": name, "exits": exits, "desc": ""})
            return

        if self.desc and line.startswith(self.desc):
            self._collecting = [line[len(self.desc):].strip()]

    def take(self, exits) -> tuple[str, str]:
        """The title for the room block that just settled, if it fits.

        Checked against the exits MIP sent: a title whose brackets disagree
        belongs to some other room, or to a character whose markers are not
        what we think they are.
        """
        theirs = sorted(e.lower() for e in exits)
        for i, held in enumerate(self._pending):
            mine = sorted(e.lower() for e in held["exits"])
            if mine and theirs and mine != theirs:
                continue
            # Anything queued before this one described a block we never saw
            # settle, so it is not coming.
            for _ in range(i + 1):
                self._pending.popleft()
            return held["name"], held["desc"]
        return "", ""
