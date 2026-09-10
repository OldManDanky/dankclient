"""Routes and hunts -- the tt++ botpath, with MIP doing the guessing."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
from mud.patrol import HEALTH_FLOOR, Bots, Stopped, make_api  # noqa: E402
from mud.session import Session  # noqa: E402


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


def test_a_step_waits_to_arrive_before_the_next_one():
    """Blasting a route at the MUD is how you end up somewhere else: each step
    waits for the room block the last one produced."""
    s, bots, api = build()

    async def scenario():
        step = asyncio.ensure_future(api["walk"]("n"))
        await asyncio.sleep(0)
        assert s.sent == ["n"]
        assert not step.done()                  # still waiting to arrive
        s._consume(mip("DDD", "s") + mip("HAB", "noun~sky~sky~exa #N"))
        s._consume(mip("FFF", "A~100"))         # settles the block
        assert await asyncio.wait_for(step, 1) is not None

    run(scenario())


def test_a_step_that_never_arrives_gives_up():
    s, bots, api = build()
    assert run(api["walk"]("n", timeout=0.05)) is None


def test_attacking_uses_the_command_the_mud_supplied():
    """HAA lists what the MUD accepts for each creature, so nothing here has
    to know 3K's verbs."""
    s, bots, api = build()
    s._consume(mip("DDD", "n")
               + mip("HAA", "npc~Cur~Cur, the dog~exa #N/consider #N/kill #N"))
    s._consume(mip("FFF", "A~100"))
    mob = s.world.room.mobs()[0]

    async def scenario():
        fight = asyncio.ensure_future(api["attack"](mob, timeout=1))
        await asyncio.sleep(0)
        assert s.sent == ["kill Cur"]
        s.world.player.enemy = ""
        s.bus.emit(events.ENEMY, "")
        assert await asyncio.wait_for(fight, 1) is True

    run(scenario())


def test_a_bot_stops_itself_when_health_drops():
    """An unattended walker that keeps stepping into rooms at ten percent is
    how a character dies."""
    s, bots, api = build()
    s.world.player.hp = int(HEALTH_FLOOR) - 1
    s.world.player.max_hp = 100

    async def scenario():
        try:
            await api["walk"]("n")
        except Stopped as why:
            assert "floor" in str(why)
            return
        raise AssertionError("walked on below the floor")

    run(scenario())
    assert s.sent == []


def test_stopping_cancels_a_running_route():
    s, bots, api = build()

    async def scenario():
        async def forever():
            while True:
                await asyncio.sleep(0.01)

        bots.start("circuit", forever, "test")
        await asyncio.sleep(0)
        assert [b["running"] for b in bots.status()] == [True]
        assert bots.stop_all() == 1
        await asyncio.sleep(0)
        assert bots.running == []

    run(scenario())


def test_reloading_a_script_stops_the_bot_it_started():
    """Otherwise editing a route leaves the old one walking and the two take
    turns steering."""
    from mud.scripts import ScriptHost
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        s, _, _ = build()
        host = ScriptHost(s, tmp)

        async def scenario():
            async def forever():
                while True:
                    await asyncio.sleep(0.01)

            from mud.scripts import Registry
            host.registries["route"] = Registry()
            host.bots.start("circuit", forever, "route")
            await asyncio.sleep(0)
            host.unload("route")
            await asyncio.sleep(0)
            assert host.bots.running == []

        run(scenario())


def test_a_speedwalk_waits_between_steps():
    """Ten commands at once is not a speedwalk: after the first step you are
    somewhere else, and the rest go out from a room they were never meant for.
    That is how /go angels ended up somewhere other than the angels."""
    s, bots, api = build()

    async def scenario():
        asyncio.ensure_future(api["follow"](["s", "s", "home"], "speedwalk"))
        await asyncio.sleep(0)
        assert s.sent == ["s"]                  # not all three

        for expected in (["s", "s"], ["s", "s", "home"]):
            s._consume(mip("DDD", "n") + mip("HAB", "noun~sky~sky~exa #N"))
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0)
            assert s.sent == expected

    run(scenario())


def test_a_speedwalk_stops_where_the_path_stops_working():
    import mud.patrol as patrol
    was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
    patrol.MOVE_TIMEOUT = patrol.LOOK_TIMEOUT = 0.05
    try:
        s2, bots2, api2 = build()

        async def scenario():
            walk = asyncio.ensure_future(api2["follow"](["n", "e", "s"], "w"))
            await asyncio.sleep(0.4)
            assert await walk is False
            # It looked to find out whether "n" had moved us, then stopped.
            assert s2.sent == ["n", "l"]

        run(scenario())
    finally:
        patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = was


def test_a_way_out_that_does_not_work_is_remembered_and_routed_around():
    """Player's map says you get to Chaos by the portal in the Palisade Pub.
    It no longer does anything.  An imported map is a hypothesis, and no
    inspection separates a stale command from a working one -- walking is
    what finds out.  (This was `home` once, and that one turned out to be
    worse than stale: it was somebody's own house.  See test_homes.)"""
    from mud.store import Store
    from mud.mapper import Mapper

    s, bots, api = build()
    store = Store()
    s.store = store
    s.mapper = m = Mapper(store)

    pub, hall = store.add_room("Pub"), store.add_room("Portal Hall")
    chaos = store.add_room("Chaos")
    store.link(pub, "enter portal", hall)  # two steps, and no longer works
    store.link(hall, "chaos", chaos)
    walk = pub                            # six steps, and does
    for i in range(5):
        step = store.add_room(f"Street {i}")
        store.link(walk, "n", step)
        walk = step
    store.link(walk, "n", chaos)
    m.here = pub

    assert m.route(chaos) == ["enter portal", "chaos"]   # the shortcut looks best
    store.mark_failed(pub, "enter portal")
    assert m.route(chaos) == ["n"] * 6                   # after failing, walk it

    store.mark_worked(pub, "enter portal")
    assert m.route(chaos) == ["enter portal", "chaos"]   # doors do reopen


def test_travelling_tries_another_way_when_a_step_goes_nowhere():
    """Not just stopping: mark the way out that failed, work the route out
    again from where we actually are, and try that.  Which both gets there
    and leaves the map better than it was found."""
    from mud.store import Store
    from mud.mapper import Mapper
    import mud.patrol as patrol

    was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
    patrol.MOVE_TIMEOUT = patrol.LOOK_TIMEOUT = 0.05
    try:
        s, bots, api = build()
        store = Store()
        s.store = store
        s.mapper = m = Mapper(store)
        here, there = store.add_room("Here"), store.add_room("There")
        store.observe(here, ["n", "shortcut"], ["a"])
        store.link(here, "n", there)             # both lead there,
        store.link(here, "shortcut", there)      # and neither works today
        m.here = here

        async def scenario():
            walk = asyncio.ensure_future(api["travel"](there, tries=2))
            assert await asyncio.wait_for(walk, 4) is False
            # Both ways were tried, and each was looked at before being
            # written off.
            assert set(s.sent) == {"n", "shortcut", "l"}
            assert all(r["failed"] for r in store.exits_from(here))

        run(scenario())
    finally:
        patrol.MOVE_TIMEOUT = was


def test_silence_is_not_taken_to_mean_you_did_not_move():
    """'embrace void' teleports you into the Tree of Life and sends no room
    block at all.  Waiting, deciding the step failed and routing again from a
    room already left is how Player ended up embracing the void four times
    in a row."""
    import mud.patrol as patrol

    was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
    patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = 0.05, 1.0
    try:
        s, bots, api = build()

        async def scenario():
            step = asyncio.ensure_future(api["walk"]("embrace void"))
            await asyncio.sleep(0.15)
            assert s.sent == ["embrace void", "l"]      # it looked
            # and the look shows somewhere new, so the step did move us
            s._consume(mip("DDD", "doorway~leave")
                       + mip("HAB", "noun~portal~portal~exa #N"))
            s._consume(mip("FFF", "A~100"))
            assert await asyncio.wait_for(step, 1) is not None

        run(scenario())
    finally:
        patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = was
