"""Routes built in the UI.  Same primitives as a script, so the two cannot
behave differently."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.botstore import Route, RouteStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402


class FakeWriter:
    def write(self, data): pass


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


# --- reading a path the way a person writes one -------------------------------


def test_a_plain_path_is_just_directions():
    assert Route(name="x", path="n n e s w").steps() == ["n", "n", "e", "s", "w"]


def test_a_repeat_count_expands():
    """Every MUD client has spelled it 3n for thirty years."""
    assert Route(name="x", path="3n 2e s").steps() == ["n", "n", "n", "e", "e", "s"]


def test_a_wild_repeat_is_capped():
    """'999n' in a path is a typo far more often than it is a plan."""
    assert len(Route(name="x", path="999n").steps()) == 99


def test_commas_allow_steps_that_are_more_than_one_word():
    """'climb pipe' moves you and is not a direction, so whitespace alone
    cannot be the separator."""
    assert Route(name="x", path="n, climb pipe, e, enter").steps() == [
        "n", "climb pipe", "e", "enter"
    ]


def test_a_repeat_only_expands_an_actual_direction():
    """A count applies only when what follows is a single word, so
    '2 handed sword' stays the one thing it obviously is -- while '2 enter',
    which is two of a real step, does repeat."""
    assert Route(name="x", path="n, 2 handed sword, e").steps() == [
        "n", "2 handed sword", "e"
    ]
    assert Route(name="x", path="2 enter").steps() == ["enter", "enter"]
    assert Route(name="x", path="3 n e").steps() == ["n", "n", "n", "e"]


def test_a_route_needs_a_name_and_somewhere_to_go():
    assert Route(name="", path="n").validate() == "give it a name"
    assert Route(name="x", path="   ").validate() == "no directions in the path"
    assert Route(name="x", path="n").validate() is None


def test_targets_may_be_typed_as_one_string():
    assert Route(name="x", path="n", targets="Cur, Cancer").targets == [
        "Cur", "Cancer"
    ]


# --- storing and running ------------------------------------------------------


def build(tmp):
    s = Session("127.0.0.1", 1, sec_code=12345)
    s.sent = []
    s._writer = FakeWriter()
    s.send = s.sent.append
    s.queue._send = s.sent.append
    host = ScriptHost(s, tmp)
    host.routes = RouteStore(host, Path(tmp) / "routes.json")
    return s, host


def test_routes_survive_a_restart():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        host.routes.upsert({"name": "circuit", "path": "n e s w",
                            "targets": ["Cur"]})

        again = RouteStore(host, Path(tmp) / "routes.json")
        again.load()
        assert [r.name for r in again.routes] == ["circuit"]
        assert again.routes[0].targets == ["Cur"]


def test_a_route_walks_its_path_and_stops_at_the_end():
    """The default is to finish.  A route that quietly starts over is one
    still walking your character around an hour later."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "short", "path": "n e"})

        async def scenario():
            assert host.routes.start(route.id) is None
            for _ in range(2):
                await asyncio.sleep(0)
                s._consume(mip("DDD", "s") + mip("HAB", "noun~sky~sky~exa #N"))
                s._consume(mip("FFF", "A~100"))
                await asyncio.sleep(0)
            await asyncio.sleep(0.05)
            assert s.sent == ["n", "e"]
            assert host.bots.running == []
            assert "finished" in host.bots.bots["short"].note

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_route_that_walks_into_a_wall_stops_rather_than_carrying_on():
    """Nothing arrived, so we are not where the path assumes.  Every step
    after that would be somewhere else entirely."""
    with tempfile.TemporaryDirectory() as tmp:
        import mud.patrol as patrol
        was = (patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT)
        patrol.MOVE_TIMEOUT = patrol.LOOK_TIMEOUT = 0.2
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "blocked", "path": "n e s"})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s") + mip("HAB", "noun~sky~sky~exa #N"))
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.9)             # the second step times out
            assert s.sent == ["n", "e", "l"]     # and it looked, to be sure
            assert "did not go anywhere" in host.bots.bots["blocked"].note

        try:
            asyncio.new_event_loop().run_until_complete(scenario())
        finally:
            patrol.MOVE_TIMEOUT, patrol.LOOK_TIMEOUT = was


def test_deleting_a_route_stops_it_walking():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "loopy", "path": "n",
                                       "loop": True})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            assert host.bots.running
            host.routes.delete(route.id)
            await asyncio.sleep(0)
            assert host.bots.running == []
            assert host.routes.routes == []

        asyncio.new_event_loop().run_until_complete(scenario())


def test_status_says_what_is_walking():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        host.routes.upsert({"name": "circuit", "path": "3n e"})
        row = host.routes.status()[0]
        assert row["step_count"] == 4
        assert row["running"] is False


def test_a_tintin_path_pastes_in_unchanged():
    """Player's Tree of Life route is semicolon separated, because that is
    what tt++ uses."""
    route = Route(name="angels", path="doorway;onward;doorway;onward;doorway")
    assert route.steps() == ["doorway", "onward", "doorway", "onward", "doorway"]


def test_targets_match_the_short_name_or_the_long_one():
    """tt++ needs two fields per target -- a long name to recognise and a
    keyword to type -- because all it has is the room description.  HAA
    carries both, so one list serves, and one entry can stand for all ten
    archangels."""
    from mud.codes import parse_haa
    from mud.patrol import wanted

    mob = parse_haa("npc~Sandalphon~Sandalphon, archangel of Malkuth "
                    "{glowing}~exa #N/consider #N/kill #N")

    assert wanted(mob, ["Sandalphon"])          # the keyword you would type
    assert wanted(mob, ["archangel"])           # anywhere in the long name
    assert wanted(mob, ["Gabriel", "archangel"])
    assert not wanted(mob, ["Gabriel"])
    assert not wanted(mob, ["Sandal"])          # half a name should not fire
    assert not wanted(mob, [""])


def test_the_kill_command_comes_from_the_mud():
    """So a route never has to know 3K's verbs, or which keyword a creature
    answers to."""
    from mud.codes import parse_haa

    mob = parse_haa("npc~Sandalphon~Sandalphon, archangel of Malkuth~"
                    "exa #N/say hi, #N/consider #N/kill #N")
    verb = next(a for a in mob.actions if a.startswith("kill"))
    assert verb.replace("#N", mob.name) == "kill Sandalphon"


def test_setup_commands_are_lines_not_words():
    """'touch angel rune' is one command, not three."""
    route = Route(name="z", path="e s",
                  setup="touch angel rune\nwear armour")
    assert route.setup_steps() == ["touch angel rune", "wear armour"]
    assert Route(name="z", path="e", setup="").setup_steps() == []


def test_a_route_runs_its_setup_before_it_walks():
    """Section Z opens by touching a rune; walking in without it is walking
    into a fight the character has not prepared for."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert(
            {"name": "sectionz", "path": "e", "setup": "touch angel rune"})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0.6)
            assert s.sent[0] == "touch angel rune"
            assert s.sent[1] == "e"

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_braced_group_is_one_step():
    """3kdb's treehouse route steps up a tree with '{pick fruit;get seed;d}',
    and 164 of its 172 routes use groups like it.  Splitting through the
    braces turns one step into three, in a path where order is everything."""
    route = Route(name="treehouse",
                  path="n;w;u;{pick fruit;get seed;d};s;ne")
    assert route.steps() == ["n", "w", "u", "pick fruit;get seed;d", "s", "ne"]


def test_a_route_walks_to_its_start_before_it_begins():
    """A path is written from one room.  Walked from anywhere else it is
    a hundred steps through the wrong part of the world."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        from mud.store import Store
        from mud.mapper import Mapper
        store = Store()
        s.store = store
        s.mapper = m = Mapper(store)
        start, away = store.add_room("Start"), store.add_room("Away")
        store.observe(start, ["n"], ["a"])
        store.observe(away, ["s"], ["b"])
        store.link(away, "s", start)
        m.here = away

        route, _ = host.routes.upsert(
            {"name": "far", "path": "n", "start": start})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            assert s.sent == ["s"]          # walking to the start, not the path

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_polite_route_waits_for_another_player_to_leave():
    """3kdb sets playercheck on every bot it defines.  Nobody wants their
    kill taken by somebody else's script."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert(
            {"name": "polite", "path": "n", "targets": ["rat"], "polite": True})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s")
                       + mip("HAA", "player~Grot~Grot the Master~exa #N")
                       + mip("HAA", "npc~rat~A rat~kill #N"))
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.05)
            assert "kill rat" not in s.sent
            assert "waiting" in host.bots.bots["polite"].note

        asyncio.new_event_loop().run_until_complete(scenario())


# --- pause and resume ---------------------------------------------------------


def line_of_rooms(s):
    """A, B, C in a row: A -n-> B -e-> C, and the way back."""
    from mud.mapper import Mapper
    from mud.store import Store
    store = Store()
    s.store = store
    s.mapper = m = Mapper(store)
    a, b, c = (store.add_room(n) for n in ("Room A", "Room B", "Room C"))
    store.observe(a, ["n"], ["a"])
    store.observe(b, ["s", "e"], ["b"])
    store.observe(c, ["w"], ["c"])
    store.link(a, "n", b)
    store.link(b, "s", a)
    store.link(b, "e", c)
    store.link(c, "w", b)
    m.here = a
    return m, a, b, c


def arrive(s, m, room):
    """A room block for the step just sent, and the map agreeing where."""
    s._consume(mip("DDD", "s") + mip("HAB", "noun~sky~sky~exa #N"))
    s._consume(mip("FFF", "A~100"))
    m.here = room


def test_pause_keeps_the_step_and_the_room_and_survives_a_restart():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            arrive(s, m, b)
            await asyncio.sleep(0.01)
            assert host.routes.pause(route.id) is None
            await asyncio.sleep(0)
            assert host.bots.running == []

        asyncio.new_event_loop().run_until_complete(scenario())
        row = host.routes.status()[0]
        assert row["paused"]["step"] == 1 and row["paused"]["room"] == b
        assert row["paused"]["room_name"] == "Room B"
        assert row["note"].startswith("paused at step 1 of 2")

        again = RouteStore(host, Path(tmp) / "routes.json")
        again.load()
        assert again.paused[route.id]["room"] == b


def test_resume_walks_back_to_that_room_and_carries_on():
    """Paused in B after its first step; somebody walked back to A.  Resume
    goes to B first, then takes the second step -- not the first again."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            arrive(s, m, b)
            await asyncio.sleep(0.01)
            host.routes.pause(route.id)
            await asyncio.sleep(0)
            m.here = a                     # walked off while it was paused
            s.sent.clear()

            assert host.routes.start(route.id, resume=True) is None
            await asyncio.sleep(0)
            assert s.sent == ["n"], "back to where it paused"
            arrive(s, m, b)
            await asyncio.sleep(0.01)
            assert s.sent == ["n", "e"], "then the next step, not the first"
            arrive(s, m, c)
            await asyncio.sleep(0.05)
            bot = host.bots.bots["line"]
            assert "finished" in bot.note and bot.steps == 2

        asyncio.new_event_loop().run_until_complete(scenario())
        assert host.routes.status()[0]["paused"] is None, "a resume uses it up"


def test_resume_does_what_the_route_does_in_that_room_first():
    """The creature it came for may be back."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert(
            {"name": "hunt", "path": "n e", "targets": ["rat"]})
        host.routes.paused[route.id] = {"step": 1, "room": b, "steps": 1,
                                        "kills": 0}
        m.here = b

        async def scenario():
            s._consume(mip("DDD", "s") + mip("HAA", "npc~rat~A rat~kill #N"))
            s._consume(mip("FFF", "A~100"))
            host.routes.start(route.id, resume=True)
            await asyncio.sleep(0.01)
            assert s.sent == ["kill rat"]

        asyncio.new_event_loop().run_until_complete(scenario())


def test_start_stop_and_a_new_path_forget_a_pause():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})
        held = {"step": 1, "room": None, "steps": 1, "kills": 0}

        host.routes.paused[route.id] = dict(held)
        host.routes.stop(route.id)
        assert route.id not in host.routes.paused, "Stop means not coming back"

        host.routes.paused[route.id] = dict(held)
        host.routes.upsert({"id": route.id, "name": "line", "path": "n e s"})
        assert route.id not in host.routes.paused, "step 1 of another path"

        host.routes.paused[route.id] = dict(held)
        host.routes.upsert({"id": route.id, "name": "renamed", "path": "n e s"})
        assert route.id in host.routes.paused, "same path, same place"

        async def scenario():
            host.routes.start(route.id)            # Start, not Resume
            await asyncio.sleep(0)
            assert s.sent == ["n"] and route.id not in host.routes.paused

        asyncio.new_event_loop().run_until_complete(scenario())


def test_it_cannot_get_back_and_keeps_the_pause():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        lost = s.store.add_room("Nowhere")          # no way to it
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})
        host.routes.paused[route.id] = {"step": 1, "room": lost, "steps": 1,
                                        "kills": 0}

        async def scenario():
            host.routes.start(route.id, resume=True)
            await asyncio.sleep(0.05)
            assert s.sent == []

        asyncio.new_event_loop().run_until_complete(scenario())
        row = host.routes.status()[0]
        assert row["paused"] and "could not get back" in row["note"]


def test_pausing_something_not_walking_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})
        assert host.routes.pause(route.id) == "it is not walking"
        assert host.routes.paused == {}


def test_it_reads_as_paused_the_moment_pause_returns():
    """The list goes back to the page straight after Pause, before the
    cancelled task has finished -- which it only does on the loop's next turn.
    Found by driving the web server's routes op, not by the store's tests."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "line", "path": "n e",
                                        "targets": ["rat"]})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            arrive(s, m, b)
            await asyncio.sleep(0.01)
            host.routes.pause(route.id)
            row = host.routes.status()[0]       # no await: still cancelling
            assert row["running"] is False and row["paused"]["room"] == b
            assert row["note"].startswith("paused at step 1")

        asyncio.new_event_loop().run_until_complete(scenario())



# --- a route that fights nothing goes as one stack ------------------------------


def test_a_route_that_fights_nothing_goes_as_one_stack():
    """With nothing to fight and nowhere to rest it is only a walk, so it goes
    the way /go does -- all of it at once -- when the map can follow it."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "stroll", "path": "n e"})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            assert s.sent == ["n", "e"], "both at once"
            arrive(s, m, c)
            await asyncio.sleep(0.05)
            bot = host.bots.bots["stroll"]
            assert "finished" in bot.note and bot.steps == 2

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_route_that_hunts_still_goes_room_by_room():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "hunt", "path": "n e",
                                       "targets": ["rat"]})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            assert s.sent == ["n"], "one step, then it looks for rats"

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_path_the_map_cannot_follow_is_walked():
    """No stack without knowing where it ends: that is what says it arrived."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        route, _ = host.routes.upsert({"name": "off map", "path": "n climb tree"})

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            assert s.sent == ["n"]

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_go_walk_rides_along_with_the_routes_and_can_be_stopped():
    """The Bot panel shows /go and map-click walks: where to, how far, Stop."""
    from mud.web import WebServer

    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        m, a, b, c = line_of_rooms(s)
        web = WebServer(s, port=0, scripts=host)
        pushed = []
        web.push = pushed.append

        async def scenario():
            assert s.travel(c, "speedwalk", "Room C")
            await asyncio.sleep(0)
            msg = web._routes_msg(host.routes)
            assert msg["walk"] == {"running": True, "goal": "Room C",
                                   "steps": 2, "note": ""}, msg["walk"]
            web._routes_op({"t": "routes", "op": "stop_walk"})
            await asyncio.sleep(0)
            assert pushed[-1]["walk"]["running"] is False

        asyncio.new_event_loop().run_until_complete(scenario())



def test_a_target_still_here_after_its_fight_is_fought_again():
    """3K stopped calling the mob our enemy while it was still at "bleeding",
    and the route walked on and left it.  3kdb's bot glances after every
    fight and fights on while a target remains; so does this."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "hunt", "path": "n e",
                                       "targets": ["rat"]})
        rat = mip("HAA", "npc~rat~A leaping rat~kill #N")

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s~e") + rat)
            s._consume(mip("FFF", "A~100"))              # the room settles
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "kill rat"
            s._consume(mip("FFF", "K~rat"))              # fighting
            s._consume(mip("FFF", "K~"))                 # ...no longer our enemy
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "glance", "looks before moving on"
            s._consume(mip("DDD", "s~e") + rat)          # and it is still there
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "kill rat", "so it fights on"
            s._consume(mip("FFF", "K~rat"))
            s._consume(mip("FFF", "K~"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "glance"
            s._consume(mip("DDD", "s~e"))                # gone now
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.05)
            assert s.sent[-1] == "e", "and only then steps on"
            assert s.sent.count("kill rat") == 2

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_target_that_will_not_fight_does_not_hold_the_route():
    """No cap on fighting -- but a kill that never starts a fight is not a
    fight, and trying it for ever would leave the route in that room."""
    import mud.patrol as patrol

    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "hunt", "path": "n e",
                                       "targets": ["rat"]})
        rat = mip("HAA", "npc~rat~A leaping rat~kill #N")
        was = patrol.START_TIMEOUT, patrol.FIGHT_POLL
        patrol.START_TIMEOUT, patrol.FIGHT_POLL = 0.05, 0.01

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s~e") + rat)
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "kill rat"
            await asyncio.sleep(0.2)                     # no fight ever starts
            assert s.sent[-1] == "glance"
            s._consume(mip("DDD", "s~e") + rat)          # still there
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.05)
            assert s.sent[-1] == "e"
            assert s.sent.count("kill rat") == 1

        try:
            asyncio.new_event_loop().run_until_complete(scenario())
        finally:
            patrol.START_TIMEOUT, patrol.FIGHT_POLL = was


def test_every_kill_is_followed_by_a_glance_before_the_next():
    """After each killing blow: glance, see it gone, see what else is here.
    The next target is picked from that glance, not the room as it was."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "hunt", "path": "n e",
                                       "targets": ["rat", "Cur"]})
        rat = mip("HAA", "npc~rat~A leaping rat~kill #N")
        cur = mip("HAA", "npc~Cur~Cur, the dog~kill #N")

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s~e") + rat + cur)
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "kill rat"
            s._consume(mip("FFF", "K~rat"))
            s._consume(mip("FFF", "K~"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "glance", "a glance after the first kill"
            s._consume(mip("DDD", "s~e") + cur)          # the rat is gone
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "kill Cur"
            s._consume(mip("FFF", "K~Cur"))
            s._consume(mip("FFF", "K~"))
            await asyncio.sleep(0.02)
            assert s.sent[-1] == "glance", "and after the second"
            s._consume(mip("DDD", "s~e"))                # clear
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.05)
            assert s.sent[-1] == "e"
            assert s.sent.count("glance") == 2
            assert host.bots.bots["hunt"].kills == 2

        asyncio.new_event_loop().run_until_complete(scenario())


def test_a_room_it_cannot_see_after_a_fight_is_not_left():
    """It moves on only once a glance has shown the room clear; with no
    answer it stops where it is rather than walking off."""
    import mud.patrol as patrol

    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        route, _ = host.routes.upsert({"name": "hunt", "path": "n e",
                                       "targets": ["rat"]})
        rat = mip("HAA", "npc~rat~A leaping rat~kill #N")
        was = patrol.LOOK_TIMEOUT
        patrol.LOOK_TIMEOUT = 0.02

        async def scenario():
            host.routes.start(route.id)
            await asyncio.sleep(0)
            s._consume(mip("DDD", "s~e") + rat)
            s._consume(mip("FFF", "A~100"))
            await asyncio.sleep(0.02)
            s._consume(mip("FFF", "K~rat"))
            s._consume(mip("FFF", "K~"))
            await asyncio.sleep(0.3)                     # glances go unanswered
            assert "e" not in s.sent
            bot = host.bots.bots["hunt"]
            assert not bot.running
            assert "did not move on" in bot.note

        try:
            asyncio.new_event_loop().run_until_complete(scenario())
        finally:
            patrol.LOOK_TIMEOUT = was
