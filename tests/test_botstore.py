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
