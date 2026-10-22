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
"""

from __future__ import annotations

import json

from .telnet import IAC, OPT_GMCP, SB, SE

#: What we ask for.  Only the room, for now: it is the package that tells us
#: something MIP cannot.  Adding to this list is how the rest arrives.
WANTED = ("Room.Info 1",)


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


def subscribe(packages=WANTED) -> bytes:
    return frame("Core.Supports.Set", list(packages))


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
    exits = body.get("exits")
    if isinstance(exits, dict):           # {"n": 1234} -- the usual shape
        exits = list(exits)
    elif isinstance(exits, str):
        exits = [e for e in exits.replace("~", " ").split() if e]
    elif not isinstance(exits, list):
        exits = []
    name = body.get("name")
    area = body.get("area")
    return {
        "num": num,
        "name": str(name) if isinstance(name, (str, int)) else "",
        "area": str(area) if isinstance(area, (str, int)) else "",
        "exits": [str(e).strip().lower() for e in exits if str(e).strip()],
    }
