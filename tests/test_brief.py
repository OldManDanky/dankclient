"""Brief mode, and a map that stayed with the player through it.

A friend testing `brief on yes` found the map standing still: "walked from
chaos ent to resid, map still thinks im at chaos ent ... caught back up when
i looked".  A capture of the same walk showed why.  In brief mode 3K sends the
room's title -- markers and all -- and its contents, but no DDD with the step:
the exits arrive only later, behind BAD's two-second sample, which is
deliberately not a new room.  So no room block ever opened.  A marked title
with no DDD of its own now makes the room itself.

The first guess was that the minimap beside the title was being read as part
of its name.  Replaying the walk through the mapper disproved it -- the map
kept up with the names mangled -- but reading the title without the minimap
is right anyway, and it stayed.  The walk below is the real one, room for room.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.markup import Markup  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"

#: (title, the row of 3K's minimap beside it, the exits MIP sends)
WALK = [
    ("North of Center (e,w,s,n)", "O-O-@-O-O-1", ["e", "w", "s", "n"]),
    ("North lane (e,w,n)", "O-@-1-O-O-", ["e", "w", "n"]),
    ("Alchemy row (w,s,n)", "1-@", ["w", "s", "n"]),
    ("Alchemy row (e,w,s,n,nw)", "v-@-O-1-O-", ["e", "w", "s", "n", "nw"]),
    ("A Break in the Haze (e,w,n)", "v-O-@-1-O-1-?", ["e", "w", "n"]),
    ("A Vortex (e,w,s,enter)", "1-E-O-^-O", ["e", "w", "s", "enter"]),
]
NAMES = ["North of Center", "North lane", "Alchemy row", "Alchemy row",
         "A Break in the Haze", "A Vortex"]


def walk(shape) -> list[str]:
    """Feed the walk through the markup, one room block at a time."""
    m = Markup()
    got = []
    for title, row, exits in WALK:
        for line in ("                     v", "                \\  | | | |",
                     shape(title, row), "                 |   |   |", ""):
            m.feed(line)
        got.append(m.take(exits)[0])
    return got


def test_brief_with_markers_but_no_closing_one():
    assert walk(lambda t, r: f"-R-_{t:<61}{r}") == NAMES


def test_brief_with_no_markers_at_all():
    assert walk(lambda t, r: f"{t:<65}{r}") == NAMES


def test_long_mode_reads_as_it_always_did():
    assert walk(lambda t, r: f"-R-_{t:<60}-R-_   {r}") == NAMES


def test_an_unmarked_title_counts_only_if_its_exits_are_the_real_ones():
    m = Markup()
    m.feed("Friend tells you: meet me at the gate (n,s)")
    assert m.take(["e", "w"]) == ("", "")


def test_a_marked_title_is_still_believed_as_before():
    """The markers are ours; a marked title with unreadable exits stays usable."""
    m = Markup()
    m.feed("-R-_A room whose title 3K cut short (u,n,w,chaos,guild")
    assert m.take(["u", "n"])[0].startswith("A room whose title")


def session() -> Session:
    return Session(prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))


# --- a step in brief mode: the title, and no DDD --------------------------------

def mip(body: str, sec: str = "12345") -> bytes:
    return f"#K%{sec}{len(body):03d}{body}".encode() + b"\n"


class Clock:
    """time.time, driven by hand, so a wait is a number rather than a sleep."""

    def __init__(self) -> None:
        import mud.session as ms
        import mud.state as st
        self.now, self._mods = 1000.0, (ms.time, st.time)
        self._was = ms.time.time
        ms.time.time = st.time.time = lambda: self.now

    def close(self) -> None:
        for mod in self._mods:
            mod.time = self._was


def rooms_of(s: Session) -> list:
    from mud import events
    got: list = []
    s.bus.on(events.ROOM, lambda room: got.append(
        (sorted(room.exits), [o.name for o in room.contents], room.opened_at)))
    return got


def test_a_brief_step_makes_its_room_from_the_title():
    """As 3K sends it with `brief on yes`: the title, the contents, a prompt,
    and the DDD only later, behind BAD's two-second sample."""
    clock = Clock()
    try:
        s = Session(sec_code=12345, jumpstart=False,
                    prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
        got = rooms_of(s)
        s._consume(b"-R-_North lane (e,w,n)" + b" " * 40 + b"-R-_   O-@-1-O-O-\r\n"
                   + mip("HAAitem~light~A tall street light~exa #N")
                   + b"A tall street light.\r\n>")
        assert got == [], "not before it has had the chance of a DDD"
        clock.now += 0.3
        s._consume(mip("BADNorth lane (e,w,n)") + mip("DDDe~w~n"))
        assert got == [(["e", "n", "w"], ["light"], 1000.0)]
    finally:
        clock.close()


def test_long_mode_still_makes_one_room_per_step():
    clock = Clock()
    try:
        s = Session(sec_code=12345, jumpstart=False,
                    prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
        got = rooms_of(s)
        s._consume(b"-R-_North lane (e,w,n)" + b" " * 40 + b"-R-_   O-@\r\n"
                   + b"-D-_A lane.\r\n-D-_\r\n")
        clock.now += 0.03
        s._consume(mip("DDDe~w~n") + mip("HAAitem~light~A tall street light~exa #N"))
        clock.now += 1.0
        s._consume(mip("FFFA~100~B~100"))
        assert len(got) == 1 and got[0][0] == ["e", "n", "w"]
    finally:
        clock.close()


def test_a_title_cut_off_mid_list_makes_no_room():
    """3K cuts long titles at sixty characters; half an exit list is how a
    phantom room was once invented."""
    clock = Clock()
    try:
        s = Session(sec_code=12345, jumpstart=False,
                    prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
        got = rooms_of(s)
        s._consume(b"-R-_Pinnacle Theatre Side Entrance (guild,n,chaos\r\n")
        clock.now += 1.0
        s._consume(mip("FFFA~100~B~100"))
        assert got == []
    finally:
        clock.close()


def test_the_last_rooms_contents_are_not_carried_over():
    clock = Clock()
    try:
        s = Session(sec_code=12345, jumpstart=False,
                    prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
        got = rooms_of(s)
        s._consume(mip("DDDn~s") + mip("HAAnpc~Cur~a dog~kill #N"))
        clock.now += 1.0
        s._consume(b"-R-_A Vortex (e,w,s,enter)" + b" " * 36 + b"-R-_  1-E-O\r\n"
                   + mip("HAAitem~coin~A single gold coin~get #N"))
        clock.now += 0.3
        s._consume(mip("FFFA~100~B~100"))
        assert got[-1][:2] == (["e", "enter", "s", "w"], ["coin"])
    finally:
        clock.close()


def test_the_session_reads_what_3k_says_the_setting_is():
    s = session()
    s._consume(b"Your brief setting is currently: [on, mapping yes]\r\n")
    assert s.brief == {"brief": "on", "mapping": "yes"}
    s._consume(b"Your brief setting is currently: [off, mapping no]\r\n")
    assert s.brief == {"brief": "off", "mapping": "no"}


def test_the_page_is_told():
    s = session()
    s._consume(b"Your brief setting is currently: [on, mapping no]\r\n")
    assert WebServer(s).snapshot()["brief"] == {"brief": "on", "mapping": "no"}


def test_character_setup_has_the_switches():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    for part in ('id="brief-desc"', 'id="brief-map"', 'id="brief-send"',
                 'id="brief-ask"', 'id="brief-now"'):
        assert part in html, part
    assert "send(`brief ${$('brief-desc').value} ${$('brief-map').value}`" in js
