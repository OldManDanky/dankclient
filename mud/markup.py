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

import re
from collections import deque

from .codes import parse_bad

#: Where a title stops and 3K's minimap starts when nothing marks the end.
#: 3K pads the title to a column before drawing the map, so the gap is wide.
GAP = re.compile(r"\s{3,}")

#: A room title with nothing to mark it: a name, then the exits in brackets,
#: then perhaps the gap and a row of the minimap.
BARE = re.compile(r"^(\S[^()]*?) \(([^()]+)\)(?:\s{3,}.*)?$")


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

    def feed(self, line: str) -> dict | None:
        """Take one line of plain text, ANSI already stripped.

        Returns the title when the line was a marked one -- the session needs
        to know, because in brief mode a title is all that arrives -- with
        "closed" saying whether its exit list was complete.  3K cuts a long
        title at sixty characters, mid-list, and exits read from half a list
        are not something to build a room from.
        """
        if self._collecting is not None:
            # A description ends at its closing marker -- on a line of its own,
            # or, as often, at the end of the last line of prose.  Only the
            # first was recognised, and a description that closed the second
            # way was taken to go on for ever: every title after it was read
            # as more description.  Brief mode, which sends no descriptions to
            # close one properly, never got its titles back at all.  A new
            # room title ends one too, whatever came before it.
            if self.room and line.startswith(self.room):
                self._finish()
            elif line.rstrip().endswith(self.desc):
                self._collecting.append(line.rstrip()[:-len(self.desc)].strip())
                self._finish()
                return None
            else:
                self._collecting.append(line.strip())
                return None

        if self.room and line.startswith(self.room):
            # The suffix is the same marker, and 3K's own ASCII map follows it
            # on the same line, so cut at the second one.  With no second one
            # -- brief mode draws the map straight after the title -- cut at
            # the gap in front of the map instead.  Without that the map was
            # read as part of the name, and a name the map had never heard of
            # made a new room at every step.
            rest = line[len(self.room):]
            end = rest.find(self.room)
            if end >= 0:
                rest = rest[:end]
            else:
                gap = GAP.search(rest.strip())
                rest = rest.strip()[:gap.start()] if gap else rest
            name, exits = parse_bad(rest.strip())
            title = {"name": name, "exits": exits, "desc": "", "strict": False,
                     "closed": rest.strip().endswith(")")}
            self._pending.append(title)
            return title

        if self.desc and line.startswith(self.desc):
            self._collecting = [line[len(self.desc):].strip()]
            return None

        # A title with no marker at all: brief mode, or a character that never
        # set them.  Read by its shape, and trusted only if the exits in its
        # brackets turn out to be exactly the ones MIP sends -- which a tell
        # with brackets in it will not manage.
        bare = BARE.match(line.rstrip())
        if bare:
            exits = [e.strip() for e in bare.group(2).split(",") if e.strip()]
            if exits:
                self._pending.append({"name": bare.group(1).strip(),
                                      "exits": exits, "desc": "",
                                      "strict": True})
        # Only a marked title is reported: an unmarked line in brackets could
        # be anybody's tell, and nothing is built from a guess.
        return None

    def _finish(self) -> None:
        """Close the description being collected, onto the title it follows."""
        if self._pending:
            self._pending[-1]["desc"] = " ".join(
                part for part in self._collecting if part)
        self._collecting = None

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
            if held.get("strict") and mine != theirs:
                continue              # an unmarked guess must match exactly
            # Anything queued before this one described a block we never saw
            # settle, so it is not coming.
            for _ in range(i + 1):
                self._pending.popleft()
            return held["name"], held["desc"]
        return "", ""
