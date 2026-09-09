"""Typed decoders for MIP line codes.

Dispatch is on the *string* code, never on a hex conversion of it.  uPortal
switches on ``text_to_hex(tag)``, which works only because AAA/FFF/CDF happen
to be valid hexadecimal -- CAP is not, so captions silently fall through to
"Unknown code!" in every uPortal build.

Formats here come from Portal's dispatch block (Main.pas ~L2374) corrected
against live 3k.org traffic.  Where the two disagree, the wire wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DELIM = "~"

# Undocumented in the v9.0 white sheet: Portal runs this substitution *before*
# splitting fields (AAB, AAD, AAG, CCF).  Without it a literal tilde cannot be
# transmitted at all.
_ESCAPE = "^^"


def unescape(s: str) -> str:
    return s.replace(_ESCAPE, DELIM)


def fields(data: str, count: int | None = None) -> list[str]:
    parts = unescape(data).split(DELIM)
    if count is not None:
        parts += [""] * (count - len(parts))
    return parts


# --- composite (FFF) ---------------------------------------------------------

# NB: tags and values *alternate*, both separated by "~":
#       FFF A~312~C~300~L~75
# The white sheet prints "FFFA312~B472" -- tag glued to value -- which is not
# what 3k.org sends.  uPortal has always parsed the real format (ptr2 = ptr+2
# skips tag *and* delimiter).
COMPOSITE_TAGS = {
    "A": "hp",        "B": "max_hp",
    "C": "sp",        "D": "max_sp",
    "E": "gp1",       "F": "max_gp1",
    "G": "gp2",       "H": "max_gp2",
    "I": "gline1",    "J": "gline2",
    "K": "enemy",     "L": "enemy_pct",  "M": "enemy_image",
    # Undocumented everywhere, found on the wire: a combat round counter.
    # Increments once per ~2s round while fighting, resets to 0 when combat
    # ends (alongside K~ clearing the enemy).  This is an authoritative
    # round tick -- no need to infer timing from message arrival.
    "N": "round",
}

NUMERIC = {
    "hp", "max_hp", "sp", "max_sp",
    "gp1", "max_gp1", "gp2", "max_gp2", "enemy_pct", "round",
}


def parse_composite(data: str) -> tuple[dict[str, object], list[str]]:
    """Return ({name: value}, [unknown tags])."""
    parts = data.split(DELIM)
    out: dict[str, object] = {}
    unknown: list[str] = []

    i = 0
    while i < len(parts):
        tag = parts[i]
        value = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2

        name = COMPOSITE_TAGS.get(tag)
        if name is None:
            if tag:
                unknown.append(tag)
            continue
        if name in NUMERIC:
            try:
                out[name] = int(value)
            except ValueError:
                out[name] = None
        else:
            out[name] = value
    return out, unknown


# --- guild-line colour markup ------------------------------------------------

COLOURS = {
    "y": "yellow", "r": "red", "b": "blue",
    "g": "green",  "c": "cyan", "v": "violet",
}

# The colour is not decoration -- 3k.org uses it semantically.
STATUS = {"r": "bad", "g": "good"}

_SPAN = re.compile(r"<([yrbgcv])([^<>]*)>")
_LABEL_TAIL = re.compile(r"(?:^|\s{2,})([^:<>]{1,40}?)\s*:\s*$")
_GAP = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class GlineField:
    label: str
    value: str
    colour: str
    status: str | None = None


def _tokens(s: str):
    pos = 0
    for m in _SPAN.finditer(s):
        if m.start() > pos:
            yield ("lit", s[pos : m.start()], "")
        yield ("span", m.group(2), m.group(1))
        pos = m.end()
    if pos < len(s):
        yield ("lit", s[pos:], "")


def parse_gline(raw: str) -> dict[str, GlineField]:
    """Lift ``Label: Value`` pairs out of a guild line.

    3k.org packs per-guild state into these, so a generic parser gets a dict of
    guild state without knowing anything about any particular guild.  Four
    shapes all occur in real traffic::

        <cMthd>: <yTiger>          label span, value span
        <gSA> : 5/5                label span, value in the following literal
        G2N: <y81094877>           label in plain text, value span
        <yAE>: <g14>/83%           value span plus a trailing fragment

    The colour of the value carries meaning: red marks a disabled or failing
    stat, green an active one.
    """
    toks = list(_tokens(raw))
    out: dict[str, GlineField] = {}

    def record(label: str, value: str, colour: str) -> None:
        label, value = label.strip(), value.strip()
        if label and value:
            out[label] = GlineField(
                label, value, COLOURS.get(colour, colour), STATUS.get(colour)
            )

    for idx, (kind, text, colour) in enumerate(toks):
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None

        # a span acting as a label: the literal after it opens with ":"
        if kind == "span" and nxt and nxt[0] == "lit" and nxt[1].lstrip().startswith(":"):
            rest = nxt[1].lstrip()[1:]
            gap = _GAP.search(rest)
            inline = (rest[: gap.start()] if gap else rest).strip()
            if inline:
                record(text, inline, "")                     # value in the literal
            else:
                after = toks[idx + 2] if idx + 2 < len(toks) else None
                if after and after[0] == "span":
                    value = after[1]
                    tail = toks[idx + 3] if idx + 3 < len(toks) else None
                    if tail and tail[0] == "lit":            # "<g14>/83%"
                        g = _GAP.search(tail[1])
                        value += tail[1][: g.start()] if g else tail[1]
                    record(text, value, after[2])
            continue

        # a span acting as a value, with its label in the preceding plain text
        if kind == "span" and idx and toks[idx - 1][0] == "lit":
            m = _LABEL_TAIL.search(toks[idx - 1][1])
            if m:
                value = text
                if nxt and nxt[0] == "lit":
                    g = _GAP.search(nxt[1])
                    value += nxt[1][: g.start()] if g else nxt[1]
                record(m.group(1), value, colour)

    return out


def gline_plain(raw: str) -> str:
    """The guild line with markup removed, for display."""
    return _SPAN.sub(lambda m: m.group(2), raw)


# --- structured records ------------------------------------------------------


@dataclass(frozen=True)
class RoomObject:
    """One HAA record -- a thing in the room.

    HAA appears in no specification and in no released client; 3k.org's mudlib
    has moved on since Portal was last built.  The action templates use "#N" as
    a placeholder for the object's name, so the MUD is telling us which
    commands are valid for each object.
    """

    kind: str            # observed: "npc"
    name: str
    description: str
    actions: list[str] = field(default_factory=list)

    def command(self, verb: str) -> str | None:
        """Resolve an action template, e.g. 'kill' -> 'kill Marble Monolith'."""
        for tmpl in self.actions:
            if tmpl.split()[0].lower() == verb.lower():
                return tmpl.replace("#N", self.name)
        return None


_MARKERS = re.compile(r"\s*[{\[]([^}\]]*)[}\]]")


def parse_enemy(raw: str) -> tuple[str, list[str]]:
    """Split an enemy name from its condition markers.

    Observed:  "Gabriel, archangel of Yesod {glowing} [scratched]"
    The braced and bracketed fragments are state -- {glowing} is a flag,
    [scratched] a health descriptor -- not part of the name.
    """
    markers = [m.group(1).strip() for m in _MARKERS.finditer(raw)]
    return _MARKERS.sub("", raw).strip(), markers


@dataclass(frozen=True)
class Tell:
    from_me: bool
    who: str
    message: str


@dataclass(frozen=True)
class Chat:
    command: str
    channel: str
    who: str
    message: str


def parse_haa(data: str) -> RoomObject:
    kind, name, desc, actions = fields(data, 4)[:4]
    return RoomObject(
        kind=kind,
        name=name,
        description=desc,
        actions=[a.strip() for a in actions.split("/") if a.strip()],
    )


#: H** records all share the same four-field shape.  HAA is interactable
#: content (items, players, npcs); HAB is scenery nouns you can examine.
ROOM_RECORD_CODES = ("HAA", "HAB")


def parse_hab(data: str) -> RoomObject:
    """Scenery noun -- same shape as HAA, different role."""
    return parse_haa(data)


def parse_bab(data: str) -> Tell:
    # observed outbound: "x~Someone~moo" -- the flag is a literal "x", not a digit
    flag, who, message = fields(data, 3)[:3]
    return Tell(from_me=flag.strip().lower() == "x", who=who, message=message)


def parse_caa(data: str) -> Chat:
    command, channel, who, message = fields(data, 4)[:4]
    return Chat(command=command, channel=channel, who=who, message=message)


def parse_bad(data: str) -> tuple[str, list[str]]:
    """"The Center of Town (e,w,s,n,d,omp,jump)" -> name and exits.

    The parentheses are only stripped when what is inside really is the exit
    list: "Behind the curtains (stage left front)" is a room whose name simply
    ends in a bracket, and cutting it would leave a name that is not the
    room's.  DDD is the authority on exits, so this is for the name.
    """
    name, sep, tail = data.rpartition(" (")
    if not sep:
        return data.strip(), []
    if not tail.endswith(")"):
        # 3K pads the title to a fixed width and cuts it there, so a long name
        # arrives with its exit list beheaded: "Pinnacle Theatre Side Entrance
        # (guild,n,chaos,fantasy,sci,gy".  The exits are unusable, but leaving
        # them welded to the name makes a room the map has never heard of.
        looks_like_exits = ("," in tail
                            and all(e and " " not in e for e in tail.split(",")))
        return (name.strip() if looks_like_exits else data.strip()), []
    exits = [e.strip().lower() for e in tail[:-1].split(",")]
    if not all(exits) or any(" " in e for e in exits):
        return data.strip(), []
    return name.strip(), exits


def parse_ddd(data: str) -> list[str]:
    """Exit list.

    The white sheet and Portal both show these space-separated ("DDDn e ne u").
    3k.org sends them tilde-delimited -- "w~d~u" -- so split on both.  Observed
    exits include non-compass verbs such as "omp" and "jump".
    """
    raw = data.replace(DELIM, " ")
    return [e for e in raw.lower().split() if e]


#: Codes carrying a single free-text value, mapped to a state attribute.
SIMPLE = {
    "AAC": "reboot",
    "AAF": "uptime",
    "BAE": "mudlag",
    "CAP": "caption",
    "BAD": "room_short",
    "BAF": "editing",
    "BAA": "combat_special",
    "BAC": "guild_special",
}

#: Gauge display names.  The white sheet calls them masks; Portal uses them as
#: the label on the corresponding gauge.
GAUGE_LABELS = {"BBA": "gp1", "BBB": "gp2", "BBC": "hp", "BBD": "sp"}

#: Codes we recognise but do not act on yet.
KNOWN_UNHANDLED = {
    "AAA", "AAD", "AAG", "AAH",            # media
    "CDF", "CCF", "CEF",                   # file transfer
}
