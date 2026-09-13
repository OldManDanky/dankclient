"""A way out is marked broken when 3K says so, not when 3K is slow.

A tester's bots kept walking him through the hyperfunk zone.  His map was
3kdb's exactly, apart from three exits marked failed -- two of them Eastwick
Road's own `e` and `w`, which work for everybody.  They had been marked
because a step and the look after it both went unanswered for a few seconds,
and a way out marked failed is routed around, so it is never walked again to
clear it: the twelve steps to Angels became thirty-two, in through the fog at
Crazy Road and out by `defunkt`.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
import mud.patrol as patrol  # noqa: E402
from mud.mapper import Mapper  # noqa: E402
from mud.outbound import NORMAL  # noqa: E402
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
def quick(move=0.05, look=0.2):
    was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
    patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = move, look
    try:
        yield
    finally:
        patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = was


#: Eastwick, as far as these tests need it: the way a bot to Angels goes, and
#: the long way round that a failed mark on Eastwick Road's `w` sent it.
EASTWICK = [
    ("Eastwick Road", ["w", "n"]),
    ("Eastwick", ["e", "void"]),
    ("Crazy Road", ["s", "fog"]),
    ("hyperfunk ZONE", ["defunkt"]),
]


def eastwick(s):
    store = Store()
    s.store = store
    s.mapper = m = Mapper(store)
    s.bus.on(events.ROOM, s._on_room)
    ids = {}
    for name, exits in EASTWICK:
        ids[name] = store.add_room(name)
        store.observe(ids[name], exits, ["sky"])
    road, wick = ids["Eastwick Road"], ids["Eastwick"]
    crazy, zone = ids["Crazy Road"], ids["hyperfunk ZONE"]
    store.link(road, "w", wick)
    store.link(wick, "e", road)
    store.link(road, "n", crazy)
    store.link(crazy, "enter fog", zone)
    store.link(zone, "defunkt", wick)
    m.here = road
    return store, m, road, wick


def as_3k(s, m, where, answer):
    """Stand in for 3K.  `answer(line, where)` gives the reply to one command
    -- bytes, or None for saying nothing at all -- and may move `where[0]`."""
    def send(line):
        s.sent.append(line)
        m.sent(line)
        reply = answer(line, where)
        if reply is not None:
            asyncio.get_running_loop().call_later(0.01, s._consume, reply)
    s.queue._send = send


def block(store, room):
    exits = dict(EASTWICK)[store.db.execute(
        "SELECT name FROM room WHERE id = ?", (room,)).fetchone()[0]]
    return mip("DDD", "~".join(exits)) + b"\r\n>\r\n"


def failed(store, room, command):
    return next(r["failed"] for r in store.exits_from(room)
                if r["command"] == command)


def test_a_slow_step_is_not_a_broken_one():
    """The tester's map, made in miniature.  Eastwick Road's `w` is fine; 3K
    is just slow to answer it, and slow to answer the look after it.  That is
    no evidence the way out is broken, and marking it so is what sent every
    later walk the long way round, through the hyperfunk zone."""
    with quick():
        s, bots, api = build()
        store, m, road, wick = eastwick(s)
        assert m.route(wick) == ["w"]
        looks = []

        def answer(line, where):
            if line == "look":
                looks.append(line)
                # The first look, before setting off, is answered; after
                # that 3K has gone quiet.
                return block(store, road) if len(looks) == 1 else None
            return None

        as_3k(s, m, [road], answer)
        assert run(asyncio.wait_for(api["travel"](wick, tries=1), 5)) is False
        assert failed(store, road, "w") == 0, "silence marked a good exit"
        assert m.route(wick) == ["w"], "and the walk after it would go round"


def test_a_step_3k_refuses_is_marked_and_routed_around():
    """"You cannot go west." is 3K saying so.  That marks the way out, and the
    walk goes the other way instead."""
    with quick():
        s, bots, api = build()
        store, m, road, wick = eastwick(s)
        moves = {("Eastwick Road", "n"): "Crazy Road",
                 ("Crazy Road", "enter fog"): "hyperfunk ZONE",
                 ("hyperfunk ZONE", "defunkt"): "Eastwick"}
        room = {name: store.db.execute("SELECT id FROM room WHERE name = ?",
                                       (name,)).fetchone()[0]
                for name, _ in EASTWICK}
        name_of = {v: k for k, v in room.items()}

        def answer(line, where):
            if line == "look":
                return block(store, where[0])
            if line == "w" and where[0] == road:
                return b"You cannot go west.\r\n>\r\n"
            to = moves.get((name_of[where[0]], line))
            if to is None:
                return None
            where[0] = room[to]
            return block(store, where[0])

        as_3k(s, m, [road], answer)
        assert run(asyncio.wait_for(api["travel"](wick, tries=3), 5)) is True
        assert failed(store, road, "w") >= 1
        assert "enter fog" in s.sent
        assert m.here == wick


def test_a_refused_command_is_not_given_the_next_room():
    """Found by the test above: the refused `w` was still waiting for a room
    when `n` brought one, took it, and the map was lost."""
    s, bots, api = build()
    store, m, road, wick = eastwick(s)
    crazy = store.db.execute("SELECT id FROM room WHERE name = 'Crazy Road'"
                             ).fetchone()[0]
    m.sent("w")
    m.refused("w")
    m.sent("n")
    m.arrived(["s", "fog"], ["sky"])
    assert m.here == crazy


def test_a_refused_step_did_not_move_you_and_needs_no_look():
    """A refusal used to be followed by a look, and the look's room -- the one
    you never left -- was taken as the step having arrived."""
    s, bots, api = build()

    async def scenario():
        step = asyncio.ensure_future(api["walk"]("w"))
        await asyncio.sleep(0)
        assert s.sent == ["w"]
        s._consume(b"You cannot go west.\r\n>\r\n")
        assert await asyncio.wait_for(step, 1) is None
        assert s.sent == ["w"], "no look: 3K has already said"

    run(scenario())


def test_a_refusal_for_some_other_direction_is_not_this_step_s():
    """Another command's refusal -- a trigger's, or the one before -- says
    nothing about this step."""
    with quick(move=0.3, look=0.3):
        s, bots, api = build()

        async def scenario():
            step = asyncio.ensure_future(api["walk"]("n"))
            await asyncio.sleep(0)
            s._consume(b"You cannot go west.\r\n>\r\n")
            await asyncio.sleep(0.05)
            assert not step.done()
            s._consume(mip("DDD", "s") + b"\r\n>\r\n")
            assert await asyncio.wait_for(step, 1) is not None

        run(scenario())


def test_a_refusal_after_a_bare_prompt_is_still_heard():
    """Some players' prompt has no line break after it, so the refusal
    arrives on the prompt's line."""
    s, bots, api = build()

    async def scenario():
        step = asyncio.ensure_future(api["walk"]("northwest"))
        await asyncio.sleep(0)
        s._consume(b"> You cannot go northwest.\r\n")
        assert await asyncio.wait_for(step, 1) is None

    run(scenario())


def test_the_look_after_a_quiet_step_goes_out_at_once():
    """It used to wait its turn in the queue, which drains on the game's
    two-second beat -- and a look is only waited on for two seconds."""
    with quick(move=0.05, look=0.5):
        s, bots, api = build()
        s.queue._hold(NORMAL, "smile")          # something already waiting

        async def scenario():
            step = asyncio.ensure_future(api["walk"]("n"))
            await asyncio.sleep(0.15)
            assert "look" in s.sent, "the look sat behind the queue"
            step.cancel()

        run(scenario())


def test_a_look_that_shows_the_same_room_marks_the_way_out():
    """Not every dead way out gets "You cannot go": `efor` is a word 3K does
    not know in that room.  The look answers, and it shows you where you
    started -- which is evidence, where silence is not."""
    with quick():
        s, bots, api = build()
        store, m, road, wick = eastwick(s)
        store.link(road, "efor", wick)
        store.db.execute("UPDATE edge SET failed = 1 WHERE from_room = ? "
                         "AND command = 'w'", (road,))
        assert m.route(wick) == ["efor"]

        def answer(line, where):
            if line == "look":
                return block(store, road)
            if line == "efor":
                return b"There is no reason to efor.\r\n>\r\n"
            return None

        as_3k(s, m, [road], answer)
        run(asyncio.wait_for(api["travel"](wick, tries=1), 5))
        assert failed(store, road, "efor") >= 1


def test_a_failed_mark_wears_off():
    store = Store()
    a, b = store.add_room("A"), store.add_room("B")
    store.link(a, "n", b)
    store.mark_failed(a, "n")
    store.mark_failed(a, "n")
    start = 1_000_000.0
    store.set_setting("failed:faded", repr(start))
    assert store.fade_failures(now=start + 3600) == 0
    assert store.fade_failures(now=start + 1.5 * Store.FADE_AFTER) == 1
    assert store.exits_from(a)[0]["failed"] == 1
    store.fade_failures(now=start + 2.1 * Store.FADE_AFTER)
    assert store.exits_from(a)[0]["failed"] == 0


def test_marks_made_by_the_old_rule_are_forgotten_once():
    """Every mark on an existing map was made by silence, so none survive the
    upgrade -- but a mark made afterwards is kept."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "map.sqlite"
        store = Store(path)
        a, b = store.add_room("Eastwick Road"), store.add_room("Eastwick")
        store.link(a, "w", b)
        store.mark_failed(a, "w")
        store.db.execute("DELETE FROM meta WHERE key = 'forgot:silent-failures'")
        store.close()

        store = Store(path)
        assert store.exits_from(a)[0]["failed"] == 0
        store.mark_failed(a, "w")
        store.close()

        store = Store(path)
        assert store.exits_from(a)[0]["failed"] == 1
        store.close()
