"""A way out that comes and goes does not make a room somewhere else.

A puddle wanders Chaos, and 3K lists it as an exit wherever it lies:
`e~w~puddle` in the Eastwick room with the void.  3kdb's map has that room as
`e,w`, so on a new player's map the room dead reckoning predicted was
"contradicted" and the map went lost.  From lost, `embrace void` could not be
followed, and the temple doorway it leads to has an identical twin -- the
start of the other Angels -- so the look could not say which.  A tester's
angels2 bot stood at its own start and stopped: "could not reach the start of
the path".
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
import mud.patrol as patrol  # noqa: E402
from mud.mapper import Mapper  # noqa: E402
from mud.patrol import Bots, make_api  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402


class FakeWriter:
    def write(self, data): pass


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


def build():
    s = Session("127.0.0.1", 1, sec_code=12345)
    s.sent = []
    s._writer = FakeWriter()
    s.send = s.sent.append
    s.queue._send = s.sent.append
    bots = Bots(s)
    return s, bots, make_api(s, bots, "test")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@contextlib.contextmanager
def quick(move=0.1, look=0.3):
    was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
    patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = move, look
    try:
        yield
    finally:
        patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = was


def test_an_extra_exit_that_is_not_a_direction_still_fits():
    store = Store()
    void = store.add_room("Eastwick")
    store.observe(void, ["e", "w"], [])
    assert store.consistent(void, ["e", "w", "puddle"], [], name="Eastwick")


def test_only_with_3k_s_title_agreeing():
    """`e~w~s~n~puddle` at Eastwick Road passed for the Eastwick next door,
    which has the same four ways out, until the title had to agree."""
    store = Store()
    wick = store.add_room("Eastwick")
    store.observe(wick, ["e", "w", "s", "n"], [])
    assert not store.consistent(wick, ["e", "w", "s", "n", "puddle"], [],
                                name="Eastwick Road")
    assert not store.consistent(wick, ["e", "w", "s", "n", "puddle"], [])


def test_an_extra_that_is_a_way_out_somewhere_is_a_different_room():
    """A vortex is a real way out, and the centre of Chaos has one."""
    store = Store()
    wick, pinnacle = store.add_room("Eastwick"), store.add_room("A Vortex")
    store.observe(wick, ["e", "w", "s", "n"], [])
    store.link(wick, "vortex", pinnacle)
    assert not store.consistent(wick, ["e", "w", "s", "n", "vortex"], [],
                                name="Eastwick")


def test_an_extra_direction_is_a_different_room():
    store = Store()
    void = store.add_room("Eastwick")
    store.observe(void, ["e", "w"], [])
    assert not store.consistent(void, ["e", "w", "n"], [], name="Eastwick")
    assert not store.consistent(void, ["e", "w", "north"], [], name="Eastwick")


def test_a_missing_exit_still_contradicts():
    store = Store()
    void = store.add_room("Eastwick")
    store.observe(void, ["e", "w"], [])
    assert not store.consistent(void, ["e", "puddle"], [], name="Eastwick")


def test_finding_a_room_from_nothing_is_not_loosened():
    """Only the room dead reckoning predicted gets the benefit of the doubt;
    picking a room out of the whole map still needs its exits exactly."""
    store = Store()
    void = store.add_room("Eastwick")
    store.observe(void, ["e", "w"], [])
    assert all(score < 1.0 or room != void
               for room, score in store.candidates(["e", "w", "puddle"], []))


def eastwick(s):
    """Eastwick Road, the room with the void, and the two identical temple
    doorways beyond it -- angels by `enter void`, angels2 by `embrace void`."""
    store = Store()
    s.store = store
    s.mapper = m = Mapper(store)
    s.bus.on(events.ROOM, s._on_room)
    road = store.add_room("Eastwick")
    void = store.add_room("Eastwick")
    angels = store.add_room("Doorway to a temple.")
    angels2 = store.add_room("Doorway to a temple.")
    store.observe(road, ["e", "w", "s", "n"], [])
    store.observe(void, ["e", "w"], [])
    store.observe(angels, ["doorway", "leave"], [])
    store.observe(angels2, ["doorway", "leave"], [])
    store.link(road, "w", void)
    store.link(void, "e", road)
    store.link(void, "enter void", angels)
    store.link(void, "embrace void", angels2)
    store.link(angels, "leave", void)
    store.link(angels2, "leave", void)
    m.here = road
    return store, m, road, void, angels2


def test_a_bot_reaches_angels2_with_a_puddle_in_the_way():
    """The tester's run, in miniature: the puddle is lying in the void room,
    `embrace void` sends no room, and the look shows a doorway that has a
    twin.  Before, this ended lost and "could not reach the start"."""
    with quick():
        s, bots, api = build()
        store, m, road, void, angels2 = eastwick(s)
        where = [road]

        # As 3K sends a room to somebody with markers set: the marked title,
        # then DDD, then the prompt.
        shown = {road: ("Eastwick", "e~w~s~n"),
                 void: ("Eastwick", "e~w~puddle"),
                 angels2: ("Doorway to a temple.", "doorway~leave")}

        def block(room):
            title, ddd = shown[room]
            return (f"-R-_{title} ({ddd.replace('~', ',')})-R-_\r\n".encode()
                    + mip("DDD", ddd) + b"\r\n>\r\n")

        def send(line):
            s.sent.append(line)
            m.sent(line)
            reply = None
            if line == patrol.LOOK:
                reply = block(where[0])
            elif line == "w" and where[0] == road:
                where[0] = void
                reply = block(void)
            elif line == "embrace void" and where[0] == void:
                where[0] = angels2           # a teleport: 3K says nothing
            if reply is not None:
                asyncio.get_running_loop().call_later(0.01, s._consume, reply)

        s.queue._send = send
        assert run(asyncio.wait_for(api["travel"](angels2), 5)) is True
        assert m.here == angels2
