"""GMCP: the other way a MUD sends structured data.

3Scapes speaks GMCP as well as MIP, and says so in its own help: the same
vitals, combat, chat and guild state, plus three things MIP cannot give --
``Room.Info`` carries the room's **number**, ``Char.Vitals`` the coffin's
corpse count, and ``Room.Death`` a kill as an event rather than a line to
recognise.  The number is the one that changes anything structural: the
whole mapper exists because nothing on 3K's wire identifies a room.

So the rule is narrow on purpose.  GMCP is the authority on *which room this
is*, and MIP stays the authority for everything it already parses against
years of captures.  Two sources for one fact is two answers that disagree.

A frame is ``IAC SB 201 <Package.Name> <space> <JSON> IAC SE``.  The package
name is ASCII and the body is UTF-8 JSON, which may be absent.

Subscribing is the client's move: ``Core.Supports.Set`` with a list of
``"Package.Name 1"`` strings.  3S answers with ``Core.Supported``, naming
every package it can send and whether we are subscribed -- which is how we
find out what it really offers, as opposed to what the help file says.

Subscribing is also the part that fails silently.  A MUD that sends only
what was asked for sends *nothing* to a client that agrees to the option
and then says nothing, which looks exactly like a MUD with no GMCP at all.
So we ask for whole roots rather than exact names -- a package added to the
game later then arrives without a new client -- and if nothing has come
back a few seconds later we ask again under the other spelling.  3S's help
calls the mechanism ``Core.Supports``; the specification and every other
client say ``Core.Supports.Set``.  One of them works, and the retry turns a
silent feed into a line that says which.
"""

from __future__ import annotations

import json

from .telnet import IAC, OPT_GMCP, SB, SE

#: What we ask for: roots, not exact package names.  "Room 1" takes
#: Room.Info, Room.Contents, Room.Map and anything else filed under Room,
#: including whatever is added to the game after this release.  Asking for
#: the whole feed costs nothing -- it arrives only when it changes -- and
#: what we do with a package is a separate decision from receiving it.
WANTED = ("Char 1", "Room 1", "Comm 1", "Guild 1",
          "Merc 1", "Craft 1", "Mud 1")

#: The spelling the specification gives, and the one 3S's help implies.
#: We send the first and fall back to the second.  See the module docstring.
VERB, VERB_ALSO = "Core.Supports.Set", "Core.Supports"

#: How long to wait for anything at all before trying the other spelling.
QUIET = 6.0


def frame(package: str, body=None) -> bytes:
    """One GMCP message, ready to write to the socket.

    Out-of-band: this is telnet negotiation, not a command, so it never goes
    through the send queue (which paces on the game's two-second beat) and
    never counts towards APM.
    """
    text = package if body is None else f"{package} {json.dumps(body)}"
    # A bare 0xFF would end the subnegotiation early, exactly as it would in
    # ordinary output.  UTF-8 cannot produce one and json.dumps escapes
    # everything above ASCII anyway, so this is belt and braces -- but the
    # rule belongs to the stream, not to whatever encodes the payload today.
    payload = text.encode("utf-8").replace(bytes([IAC]), bytes([IAC, IAC]))
    return bytes([IAC, SB, OPT_GMCP]) + payload + bytes([IAC, SE])


def hello(version: str, name: str = "Dank Mud Client") -> bytes:
    return frame("Core.Hello", {"client": name, "version": version})


def subscribe(packages=WANTED, verb: str = VERB) -> bytes:
    return frame(verb, list(packages))


def parse(payload: bytes) -> tuple[str, object]:
    """(package, body) from a frame's payload.  Body is None when there is
    none, and when it is not JSON we can read -- the package name is still
    worth having, and a frame we cannot decode must not take the session
    with it."""
    try:
        text = payload.decode("utf-8", "replace").strip()
    except Exception:                      # pragma: no cover -- replace never raises
        return "", None
    if not text:
        return "", None
    package, _, rest = text.partition(" ")
    rest = rest.strip()
    if not rest:
        return package, None
    try:
        return package, json.loads(rest)
    except (ValueError, TypeError):
        return package, None


def room_info(body) -> dict | None:
    """``Room.Info`` as the map wants it, or None if it is not usable.

    ``num`` is the whole point, so a frame without a number it can believe is
    not a room block -- better to fall back on the mapper's own reckoning
    than to file the room under 0.
    """
    if not isinstance(body, dict):
        return None
    try:
        num = int(body.get("num"))
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    raw = body.get("exits")
    ways: dict[str, int] = {}
    if isinstance(raw, dict):
        # The real shape: direction -> the room it leads to.  A 0 means the
        # exit is there and the MUD is not saying where it goes, which is
        # the frontier a mapper wants, not an absence.
        for way, dest in raw.items():
            key = str(way).strip().lower()
            if not key:
                continue
            try:
                ways[key] = int(dest)
            except (TypeError, ValueError):
                ways[key] = 0
    elif isinstance(raw, str):
        ways = {e: 0 for e in
                (w.strip().lower() for w in raw.replace("~", " ").split()) if e}
    elif isinstance(raw, list):
        ways = {e: 0 for e in
                (str(w).strip().lower() for w in raw) if e}
    name = body.get("name")
    area = body.get("area")
    return {
        "num": num,
        "name": str(name) if isinstance(name, (str, int)) else "",
        "area": str(area) if isinstance(area, (str, int)) else "",
        "exits": list(ways),
        # Only the ones it actually named.  Nothing downstream may read a
        # missing direction as "no exit": hidden exits are left out, so a
        # room with nothing but hidden ways out reports none at all.
        "ways": {w: d for w, d in ways.items() if d > 0},
    }


#: Most of a payload kept as the sample.  Enough to see the shape of one.
SAMPLE = 400

#: Most field names remembered per package.  A package that names a field
#: after its contents -- a map legend's glyphs, a guild's numbered slots --
#: would otherwise grow this list for as long as the session runs.
FIELDS = 60


def paths(body, prefix: str = "") -> list[str]:
    """Every field path in a payload: ``hp``, ``exits.n``, ``items[].name``.

    An index is flattened to ``[]`` on purpose -- what is worth knowing is
    that the package carries a list of things with names, not how many
    things were in it this time.
    """
    out: list[str] = []
    if isinstance(body, dict):
        for key, value in body.items():
            here = f"{prefix}{key}"
            kids = paths(value, here + ".")
            out.extend(kids or [here])
    elif isinstance(body, list):
        for item in body:
            for found in paths(item, prefix.rstrip(".") + "[]."):
                if found not in out:
                    out.append(found)
        if not out and prefix:
            out.append(prefix.rstrip(".") + "[]")
    return out


class Audit:
    """What was asked for, what the MUD said it would send, and what came.

    The three are routinely different, and only the first is visible without
    writing it down.  A package can be offered and never sent because nothing
    about it changed; the whole feed can be silent because the subscription
    never landed; and both look the same from the screen -- nothing happens --
    while needing opposite fixes.  So the client keeps the receipts.
    """

    def __init__(self) -> None:
        self.negotiated = False
        self.verb = ""
        self.asked: list[str] = []
        #: The body of ``Core.Supported``: what the MUD says it can send.
        self.offered: object = None
        self.frames = 0
        self.unreadable = 0
        #: package -> {"count", "first_at", "last_at", "last", "fields"}
        self.seen: dict[str, dict] = {}

    def subscribed(self, verb: str, packages) -> None:
        self.verb, self.asked = verb, list(packages)

    def took(self, package: str, body, at: float) -> None:
        row = self.seen.get(package)
        if row is None:
            row = self.seen[package] = {"count": 0, "first_at": at,
                                        "last_at": at, "last": "",
                                        "fields": []}
        row["count"] += 1
        row["last_at"] = at
        text = json.dumps(body, sort_keys=True) if body is not None else ""
        row["last"] = text[:SAMPLE] + ("..." if len(text) > SAMPLE else "")
        if len(row["fields"]) <= FIELDS:
            for field in paths(body):
                if field not in row["fields"]:
                    row["fields"].append(field)
                    if len(row["fields"]) > FIELDS:
                        row["fields"].append("...")
                        break

    @property
    def anything(self) -> bool:
        """Has the MUD sent us a single frame?  The question the fallback
        spelling turns on: negotiated and silent is the failure that looks
        like success."""
        return bool(self.seen)

    def report(self) -> list[str]:
        """``/gmcp``, as lines."""
        if not self.negotiated:
            return ["GMCP: not negotiated -- this MUD did not offer it."]
        out = [f"GMCP: negotiated, {self.frames} frame(s) in"
               + (f", {self.unreadable} unreadable" if self.unreadable else "")]
        out.append(f"  asked ({self.verb}): " + ", ".join(self.asked))
        if self.offered is None:
            out.append("  the MUD has not answered with Core.Supported")
        else:
            offers = (self.offered if isinstance(self.offered, list)
                      else [str(self.offered)])
            out.append("  it offers: " + ", ".join(str(o) for o in offers))
            bare = {str(o).split()[0].split(".")[0] for o in offers}
            mine = {a.split()[0].split(".")[0] for a in self.asked}
            missed = sorted(bare - mine)
            if missed:
                out.append("  offered and not asked for: " + ", ".join(missed))
        if not self.seen:
            out.append("  nothing has arrived yet")
            return out
        out.append("  arrived:")
        for package in sorted(self.seen):
            row = self.seen[package]
            out.append(f"    {package}  x{row['count']}")
            if row["fields"]:
                out.append("      fields: " + ", ".join(row["fields"]))
            if row["last"]:
                out.append("      last:   " + row["last"])
        return out
