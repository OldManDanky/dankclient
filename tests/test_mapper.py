"""Dead reckoning.  Most of these pin behaviour that a real walk exposed and
that looks perfectly reasonable when you get it wrong."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402
from walk_fixture import WALK  # noqa: E402


def fresh():
    """A map that may grow: the client's own is locked (it is 3kdb's), and
    this is what /unlock leaves you with -- where the growing is tested."""
    store = Store()
    store.locked = False
    return store, Mapper(store)


# --- attributing a room block to a command ------------------------------------


def test_two_commands_in_flight_are_matched_in_order():
    """You send 'w' then 'n' before either reply lands.  A single pending slot
    would lose the first move; the queue keeps both in order."""
    store, m = fresh()
    m.arrived(["n", "e", "w"], ["sky"], at=0.0)
    first = m.here

    m.sent("w", at=1.0)
    m.sent("n", at=1.3)
    second = m.arrived(["e"], ["road"], at=1.4)
    third = m.arrived(["s"], ["gate"], at=1.5)

    assert store.destination(first, "w") == second
    assert store.destination(second, "n") == third


def test_the_step_is_blamed_rather_than_the_housekeeping_beside_it():
    """A route sends its tidying and its next move in one breath -- "wrap
    all", "disperse corpse", "divvy gold", "w".  Only the last of them moves,
    and oldest-first hands the block to "wrap all": the room has no such way
    out, so the map cannot place it, and the client is lost with a perfectly
    good "w" three places down the queue.  On the chessboard route that
    happened at every kill."""
    store, m = fresh()
    m.arrived(["n", "e", "w"], ["sky"], at=0.0)
    start = m.here

    for junk in ("wrap all", "disperse corpse", "divvy gold"):
        m.sent(junk, at=1.0)
    m.sent("w", at=1.0)

    landed = m.arrived(["e"], ["road"], at=1.1)
    assert landed is not None, "lost, with the move still in the queue"
    assert store.destination(start, "w") == landed
    assert not m._pending, "the tidying is still queued to spoil the next one"


def test_a_way_out_is_not_reordered_past_an_earlier_one():
    """Skipped, never reordered: two moves in flight arrive in the order they
    were sent, and picking the newer would swap them."""
    store, m = fresh()
    m.arrived(["n", "e", "w"], ["sky"], at=0.0)
    first = m.here
    m.sent("n", at=1.0)
    m.sent("e", at=1.1)
    second = m.arrived(["s"], ["road"], at=1.2)
    assert store.destination(first, "n") == second


def test_a_command_nobody_knows_is_still_the_best_guess():
    """3K's exits are what DDD says they are, but a route can walk something
    neither DDD nor the map has heard of.  Falling back to the oldest is no
    worse than the guess we would have made anyway."""
    store, m = fresh()
    m.arrived(["n", "e"], ["sky"], at=0.0)
    first = m.here
    m.sent("squeeze through the crack", at=1.0)
    second = m.arrived(["s"], ["cave"], at=1.1)
    assert second is not None and second != first
    assert store.destination(first, "squeeze through the crack") == second


def test_a_command_that_produced_nothing_is_forgotten():
    """Sessions open with 'l', 'jump' and a pile of 'aset' lines, none of which
    move you.  Left in the queue they misattribute every arrival that follows,
    silently, for the rest of the session."""
    store, m = fresh()
    m.arrived(["n"], ["sky"], at=0.0)
    start = m.here

    for i, junk in enumerate(["l", "jump", "aset look_item reset"]):
        m.sent(junk, at=1.0 + i)
    m.sent("n", at=10.0)
    landed = m.arrived(["s"], ["road"], at=10.1)

    assert store.destination(start, "n") == landed
    assert [e["command"] for e in store.exits_from(start)] == ["n"]


def test_a_failed_move_creates_no_exit():
    """Player walked south into a wall, waited, then went west instead."""
    store, m = fresh()
    m.arrived(["w"], ["sky"], at=0.0)
    start = m.here

    m.sent("s", at=1.0)                       # no room block follows
    m.sent("w", at=3.4)
    m.arrived(["e"], ["road"], at=3.5)

    assert store.destination(start, "s") is None
    assert [e["command"] for e in store.exits_from(start)] == ["w"]


def test_look_does_not_become_an_exit():
    """A look redisplays the room.  Credited with the next block it would draw
    an exit from a room to itself."""
    store, m = fresh()
    m.arrived(["n"], ["sky"], at=0.0)
    here = m.here

    m.sent("look", at=1.0)
    assert m.arrived(["n"], ["sky"], at=1.1) == here
    assert store.exits_from(here) == []


def test_an_uncaused_block_is_evidence_not_an_arrival():
    """The MUD redisplays the room after a kill.  It should not count as a
    visit, and it must not move us."""
    store, m = fresh()
    m.arrived(["n"], ["sky"], at=0.0)
    here = m.here
    visits = store.room(here)["visits"]

    assert m.arrived(["n"], ["sky"], at=30.0) == here
    assert store.room(here)["visits"] == visits


# --- being lost ---------------------------------------------------------------


def test_the_first_room_of_a_session_is_simply_new():
    store, m = fresh()
    assert m.arrived(["n", "s"], ["sky"], at=0.0) is not None
    assert store.room(m.here)["visits"] == 1


def test_a_unique_fingerprint_relocates_you():
    store, m = fresh()
    m.arrived(["n", "s"], ["altar", "pews"], at=0.0)
    home = m.here

    m.here = None                              # teleported, died, reconnected
    assert m.arrived(["n", "s"], ["altar", "pews"], at=5.0) == home


def test_an_ambiguous_fingerprint_leaves_you_lost():
    """Two chessboard squares look identical.  Guessing one would invent
    edges that do not exist."""
    store, m = fresh()
    dark = store.add_room("A Dark Square")
    light = store.add_room("A Light Square")
    for room in (dark, light):
        store.observe(room, ["n", "s", "e", "w"], ["tiles"])

    assert m.arrived(["n", "s", "e", "w"], ["tiles"], at=0.0) is None
    assert sorted(m.candidates) == sorted([dark, light])


def test_moving_narrows_the_candidates_down():
    """Lost among identical squares, one move that only one candidate could
    have made settles it."""
    store, m = fresh()
    dark, light, north = (store.add_room(), store.add_room(), store.add_room())
    for room in (dark, light):
        store.observe(room, ["n", "s", "e", "w"], ["tiles"])
    store.observe(north, ["s"], ["wall"])
    store.link(dark, "n", north)               # only the dark square goes north

    assert m.arrived(["n", "s", "e", "w"], ["tiles"], at=0.0) is None
    m.sent("n", at=1.0)
    assert m.arrived(["s"], ["wall"], at=1.1) == north
    assert m.candidates == []


# --- edges --------------------------------------------------------------------


def test_a_multi_word_command_is_an_edge_like_any_other():
    """'climb pipe' moves you and appears in no exit list, which is why the
    mapper never tries to recognise movement commands."""
    store, m = fresh()
    m.arrived(["e", "w"], ["street"], at=0.0)
    street = m.here
    m.sent("climb pipe", at=1.0)
    board = m.arrived(["n", "s", "e", "w"], ["tiles"], at=1.1)
    assert store.destination(street, "climb pipe") == board


def test_routing_crosses_ordinary_and_special_exits_alike():
    store, m = fresh()
    m.arrived(["n"], ["a"], at=0.0)
    a = m.here
    m.sent("n", at=1.0)
    m.arrived(["s", "enter"], ["b"], at=1.1)
    b = m.here
    m.sent("enter", at=2.0)
    m.arrived(["leave"], ["c"], at=2.1)
    c = m.here
    assert m.route(c, start=a) == ["n", "enter"]
    assert m.route(a, start=c) is None          # no way back was ever walked


# --- the real walk ------------------------------------------------------------


def replay_walk():
    store, m = fresh()
    for event in WALK:
        if event[0] == "sent":
            m.sent(event[2], at=event[1])
        else:
            _, at, exits, scenery = event
            m.arrived(exits, scenery, at=at)
    return store, m


def test_the_town_walk_accounts_for_every_block():
    """42 room blocks, 41 of them moves.  The odd one out is the `l` Player
    typed at the end: a look redisplays the room, so it is evidence about
    where he already stood and not a forty-second arrival."""
    store, _ = replay_walk()
    blocks = sum(1 for e in WALK if e[0] == "room")
    arrivals = store.db.execute("SELECT SUM(visits) s FROM room").fetchone()["s"]
    looks = sum(1 for e in WALK if e[0] == "sent" and e[2] in ("l", "look"))
    assert (blocks, arrivals, looks) == (42, 41, 1)


def test_the_town_walk_never_gives_a_room_two_exit_sets():
    """One room holding two different exit lists means two rooms were merged
    -- the failure the whole design exists to avoid."""
    store, _ = replay_walk()
    muddled = store.db.execute(
        "SELECT room_id FROM fingerprint GROUP BY room_id "
        "HAVING COUNT(DISTINCT exits) > 1"
    ).fetchall()
    assert [r["room_id"] for r in muddled] == []


def test_the_town_walk_is_reversible_wherever_it_was_walked_both_ways():
    """The strongest check the data can give: every time Player walked a
    direction and then walked back, he arrived where he started."""
    store, _ = replay_walk()
    opposite = {"n": "s", "s": "n", "e": "w", "w": "e", "u": "d", "d": "u"}
    checked = 0
    for edge in store.db.execute("SELECT * FROM edge"):
        back = opposite.get(edge["command"])
        if back is None:
            continue
        home = store.destination(edge["to_room"], back)
        if home is None:
            continue
        checked += 1
        assert home == edge["from_room"], (
            f"{edge['from_room']} -{edge['command']}-> {edge['to_room']} "
            f"-{back}-> {home}"
        )
    assert checked >= 12


# --- wired into a live session ------------------------------------------------


def mip(code, body, sec="12345"):
    data = f"{code}{body}"
    return f"#K%{sec}{len(data):03d}{data}".encode("latin-1")


def test_a_session_maps_as_the_bytes_arrive():
    """MIP bytes in, a map out -- through the telnet filter, the scanner, the
    world and the mapper, with nothing replayed by hand."""
    from mud.session import Session

    class FakeWriter:
        def write(self, data): pass

    store = Store()
    store.locked = False                    # so the walking below maps
    s = Session("127.0.0.1", 1, sec_code=12345, store=store)
    s._writer = FakeWriter()

    # Real traffic, in the order the wire sends it: the room block, then BAD
    # naming where you now are, then the refresh DDD that always trails it.
    s._consume(mip("DDD", "n~e") + mip("HAB", "noun~sky~sky~exa #N"))
    s._consume(mip("BAD", "North lane (n,e)"))
    s._consume(mip("DDD", "n~e"))                  # refresh, not a new room
    s.send("n")
    s._consume(mip("DDD", "s") + mip("HAB", "noun~wall~wall~exa #N"))
    s._consume(mip("FFF", "A~100"))               # settles the second block

    status = s.mapper.status()
    assert status["known_rooms"] == 2 and status["edges"] == 1
    assert not status["lost"]

    lane = store.db.execute(
        "SELECT id, name FROM room WHERE name IS NOT NULL"
    ).fetchone()
    assert lane["name"] == "North lane"          # not "North lane (n,e)"
    assert store.destination(lane["id"], "n") == status["room"]


def test_a_room_with_nothing_in_it_is_still_mapped():
    """A DDD with no records at all still has to settle, or one bare room puts
    dead reckoning off by one for the rest of the session."""
    from mud.session import Session

    class FakeWriter:
        def write(self, data): pass

    store = Store()
    store.locked = False                    # so the walking below maps
    s = Session("127.0.0.1", 1, sec_code=12345, store=store)
    s._writer = FakeWriter()

    s._consume(mip("DDD", "n"))
    s.send("n")
    s._consume(mip("DDD", "s"))
    s._consume(mip("FFF", "A~100"))

    assert s.mapper.status()["known_rooms"] == 2


def test_mapping_can_be_switched_off_entirely():
    from mud.session import Session

    s = Session("127.0.0.1", 1, sec_code=12345)
    assert s.mapper is None
    s._consume(mip("DDD", "n~e"))               # must not raise


def test_the_drawn_neighbourhood_includes_where_you_came_from():
    """Edges are directed, but a room you walked in from is still next door on
    the page.  Without this, arriving somewhere with no exit back drew a map
    holding exactly one room."""
    store, m = fresh()
    m.arrived(["e"], ["street"], at=0.0)
    first = m.here
    m.sent("e", at=1.0)
    m.arrived(["w"], ["hall"], at=1.1)

    view = m.neighbourhood()
    assert set(view["rooms"]) == {first, m.here}
    assert view["rooms"][first]["exits"] == {"e": m.here}
    assert view["rooms"][m.here]["exits"] == {}   # nothing leads back yet
    assert m.route(first) is None                 # and routing knows it


def test_the_neighbourhood_stops_at_the_radius():
    store, m = fresh()
    m.arrived(["e"], ["a"], at=0.0)
    start = m.here
    for i in range(6):
        m.sent("e", at=10.0 + i)
        m.arrived(["e", "w"], [f"room{i}"], at=10.05 + i)
    assert len(m.neighbourhood(radius=2, centre=start)["rooms"]) == 3


def test_exits_nobody_has_walked_are_reported_separately():
    """DDD lists every way out; an edge exists only once you have taken one.
    The difference is where there is still something to find."""
    store, m = fresh()
    m.arrived(["n", "e", "enter"], ["sky"], at=0.0)
    start = m.here
    m.sent("n", at=1.0)
    m.arrived(["s"], ["hall"], at=1.1)

    view = m.neighbourhood()["rooms"][start]
    assert view["exits"] == {"n": m.here}
    assert sorted(view["unwalked"]) == ["e", "enter"]


def test_a_room_reports_the_exits_it_is_seen_with_most_often():
    """Exits can arrive garbled once; the map should not treat a single odd
    reading as the truth about a room."""
    store, m = fresh()
    room = store.add_room()
    store.observe(room, ["n", "s"], ["sky"])
    store.observe(room, ["n", "s"], ["sky"])
    store.observe(room, ["n"], ["sky"])
    assert store.exits_of(room) == ["n", "s"]


def test_rooms_can_be_found_by_name_nearest_first():
    """Names are not unique -- 3K has two Alchemy rows -- so every reachable
    match comes back, closest first."""
    store, m = fresh()
    m.arrived(["n"], ["start"], at=0.0)
    walk = [("n", ["n", "s"], ["a"]), ("n", ["n", "s"], ["b"]),
            ("n", ["s"], ["c"])]
    for i, (cmd, exits, scen) in enumerate(walk):
        m.sent(cmd, at=10.0 + i)
        m.arrived(exits, scen, at=10.05 + i)
    far, near = m.here, store.db.execute(
        "SELECT id FROM room ORDER BY id").fetchall()[1]["id"]
    store.rename(far, "Alchemy row")
    store.rename(near, "Alchemy row")

    m.here = store.db.execute("SELECT MIN(id) i FROM room").fetchone()["i"]
    found = m.find_rooms("alchemy")
    assert [r[0] for r in found] == [near, far]
    assert found[0][2] < found[1][2]


def test_a_room_with_no_way_there_is_not_offered():
    store, m = fresh()
    m.arrived(["n"], ["here"], at=0.0)
    stranded = store.add_room("Temple of Hod")
    assert m.find_rooms("temple") == []
    assert m.route(stranded) is None


# --- areas --------------------------------------------------------------------


def corridor(m, steps):
    for i, (cmd, exits) in enumerate(steps):
        m.sent(cmd, at=100.0 + i)
        m.arrived(exits, [f"scene{i}"], at=100.05 + i)


def test_an_area_stops_at_an_exit_with_no_direction_to_it():
    """The nine steps into 3K's chessboard include two that are not compass
    moves, and those are exactly the two that cross into somewhere new."""
    store, m = fresh()
    m.arrived(["n", "enter"], ["street"], at=0.0)
    start = m.here
    corridor(m, [("n", ["n", "s"]), ("n", ["s"])])
    town = set(m.area(start=start))

    m.here = start
    m.sent("enter", at=200.0)
    m.arrived(["leave"], ["elsewhere"], at=200.05)
    inside = m.here

    assert inside not in town
    assert len(town) == 3


def test_an_area_does_not_swallow_one_that_is_already_labelled():
    store, m = fresh()
    m.arrived(["n"], ["a"], at=0.0)
    first = m.here
    corridor(m, [("n", ["n", "s"]), ("n", ["s"])])
    theirs = store.add_region("Somewhere else")
    store.assign([m.here], theirs)

    claimed = m.area(start=first)
    assert m.here not in claimed
    assert first in claimed


def test_areas_nest_and_refuse_to_loop():
    s = Store()
    chaos = s.add_region("Chaos")
    tree = s.add_region("Tree of Life", parent_id=chaos)
    room = s.add_room("Temple of Malkuth")
    s.assign([room], tree)
    assert s.region_path(room) == ["Chaos", "Tree of Life"]

    assert s.reparent(chaos, tree) is not None      # would be its own ancestor
    assert s.region_path(room) == ["Chaos", "Tree of Life"]


def test_the_region_tree_counts_rooms_at_each_level():
    s = Store()
    chaos = s.add_region("Chaos")
    tree = s.add_region("Tree of Life", parent_id=chaos)
    s.assign([s.add_room(), s.add_room()], chaos)
    s.assign([s.add_room()], tree)
    assert [(d, r["name"], n) for d, r, n in s.region_tree()] == [
        (0, "Chaos", 2), (1, "Tree of Life", 1)
    ]


# --- moved by something we cannot see -----------------------------------------


def test_a_teleport_does_not_get_stamped_onto_the_room_you_left():
    """`embrace void` moved Player, and the room block only arrived when he
    typed `l` nine seconds later -- uncaused, as far as the mapper could tell.
    Trusting it as a redisplay wrote the far end of the teleport onto Eastwick,
    which then held two different exit sets."""
    store, m = fresh()
    m.arrived(["e", "w"], ["sky"], at=0.0)
    eastwick = m.here

    m.sent("embrace void", at=10.0)              # times out, causes nothing
    m.sent("l", at=20.0)                         # filtered: looks do not move
    landed = m.arrived(["doorway", "leave"], ["portal"], at=20.1)

    assert landed != eastwick
    assert store.db.execute(
        "SELECT COUNT(*) c FROM fingerprint WHERE room_id = ?", (eastwick,)
    ).fetchone()["c"] == 1


def test_a_genuine_redisplay_is_still_treated_as_one():
    store, m = fresh()
    m.arrived(["n", "s"], ["sky", "road"], at=0.0)
    here = m.here
    visits = store.room(here)["visits"]
    assert m.arrived(["n", "s"], ["sky", "road"], at=60.0) == here
    assert store.room(here)["visits"] == visits


def test_scenery_that_has_drifted_still_counts_as_the_same_room():
    """Redisplays after a kill lose the corpse; that is not a new room."""
    store, m = fresh()
    m.arrived(["n"], ["sky", "road", "litter"], at=0.0)
    here = m.here
    assert m.arrived(["n"], ["sky", "road"], at=30.0) == here


def test_two_bare_rooms_with_the_same_exits_are_not_the_same_room():
    """Neither reports any scenery.  That is absence of evidence, and reading
    it as proof of sameness makes every bare corridor interchangeable."""
    store, m = fresh()
    m.arrived([], [], at=0.0)
    first = m.here
    m.sent("w", at=1.0)
    second = m.arrived([], [], at=1.1)
    assert second != first


def test_a_bare_room_you_walk_back_into_is_still_recognised():
    """Dead reckoning knows where 'e' goes; a room with no scenery does not
    contradict that, so the prediction stands."""
    store, m = fresh()
    m.arrived(["e"], ["gate"], at=0.0)
    start = m.here
    m.sent("e", at=1.0)
    bare = m.arrived(["w", "e"], [], at=1.1)
    m.sent("w", at=2.0)
    m.arrived(["e"], ["gate"], at=2.1)
    m.sent("e", at=3.0)
    assert m.arrived(["w", "e"], [], at=3.1) == bare


def test_the_drawn_neighbourhood_is_capped():
    """Ten moves is nothing in a corridor and a tenth of the world in an open
    one -- 4,949 rooms on the imported map, rebuilt several times a second to
    draw a panel that holds sixty."""
    store, m = fresh()
    rooms = [store.add_room(f"room {i}") for i in range(60)]
    for room in rooms:                       # a clique: everything adjacent
        store.observe(room, ["n"], [f"scene{room}"])
        for other in rooms:
            if other != room:
                store.link(room, f"to{other}", other)
    m.here = rooms[0]
    assert len(m.neighbourhood(limit=25)["rooms"]) == 25
    assert len(m.neighbourhood(limit=1000)["rooms"]) == 60


def test_the_room_count_does_not_collide_with_the_drawn_map():
    """Both wanted to be called "rooms".  A count arriving where the browser
    expects a map reads to it as a server too old to send one."""
    store, m = fresh()
    m.arrived(["n"], ["sky"], at=0.0)
    assert isinstance(m.status()["known_rooms"], int)
    assert "rooms" not in m.status()
    assert isinstance(m.neighbourhood()["rooms"], dict)


# --- a map that is already finished -------------------------------------------


def test_a_locked_map_does_not_invent_rooms():
    """An imported map is somebody's years of walking.  A room it does not
    contain is far likelier to be one we failed to recognise, and inventing it
    adds a duplicate of a room already there that nothing later joins up."""
    store, m = fresh()
    known = store.add_room("A Vortex")
    store.observe(known, ["e", "enter"], ["vortex"])
    store.locked = True

    assert m.arrived(["n", "s"], ["somewhere else"], at=0.0) is None
    assert m.here is None
    assert store.db.execute("SELECT COUNT(*) c FROM room").fetchone()["c"] == 1


def test_a_locked_map_still_recognises_what_it_knows():
    store, m = fresh()
    room = store.add_room("A Vortex")
    store.observe(room, ["e", "enter"], ["vortex"])
    store.locked = True
    assert m.arrived(["e", "enter"], ["vortex"], at=0.0) == room


def test_walking_off_a_locked_map_loses_you_rather_than_extending_it():
    store, m = fresh()
    a = store.add_room("A")
    store.observe(a, ["n"], ["here"])
    store.locked = True
    m.arrived(["n"], ["here"], at=0.0)
    assert m.here == a

    m.sent("n", at=1.0)
    assert m.arrived(["s"], ["unmapped"], at=1.1) is None
    assert m.here is None
    assert store.db.execute("SELECT COUNT(*) c FROM room").fetchone()["c"] == 1


def test_the_lock_travels_with_the_map():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "3k.sqlite"
        s = Store(path)
        s.locked = True
        s.close()
        assert Store(path).locked is True


def test_a_named_arrival_finds_you_in_a_map_you_have_never_walked():
    """The room title arrives with every room and arrives at once, where BAD
    names fewer than half of them and does it on the tick.  In a fifty
    thousand room map that is the difference between the first room and the
    third."""
    store, m = fresh()
    room = store.add_room("A quiet cul de sac")
    store.observe(room, ["n", "s"], [])       # imported: exits, no scenery
    store.locked = True

    assert m.arrived(["n", "s"], ["cobbles"], name="A quiet cul de sac",
                     at=0.0) == room


def test_a_name_that_matches_nothing_still_leaves_you_lost():
    store, m = fresh()
    store.add_room("Somewhere")
    store.locked = True
    assert m.arrived(["n"], [], name="Nowhere at all", at=0.0) is None


def test_a_map_is_locked_before_anybody_says_so():
    """A tester's client put him in the wrong room and then walked him
    somewhere else entirely.  A map that grows while you walk is how the wrong
    room gets there, and nobody thinks to lock a map they were not told was
    open."""
    store = Store()
    assert store.locked is True, "a map nobody has touched is 3kdb's"
    store.locked = False
    assert store.locked is False, "and /unlock still opens it"


def test_a_locked_map_does_not_grow_even_for_a_room_it_has_never_heard_of():
    """The map is 3kdb's and stays 3kdb's: what 3K has gained comes in
    through Options -> Updates, not from a guess made while walking.  Not
    recognising a room is being lost, and being lost resolves itself."""
    store, m = fresh()
    here = store.add_room("Lord's promenade")
    store.observe(here, ["n", "s", "w"], [])
    store.locked = True
    m.arrived(["n", "s", "w"], [], name="Lord's promenade", at=0.0)
    rooms = store.db.execute("SELECT count(*) FROM room").fetchone()[0]

    m.sent("w", at=1.0)
    found = m.arrived(["w"], ["pews"],
                      name="The Chapel of the Three Kingdoms", at=1.1)

    assert found is None, "lost, rather than a room invented"
    assert store.db.execute("SELECT count(*) FROM room").fetchone()[0] == rooms
    assert store.destination(here, "w") is None, "and no edge to it either"


def test_a_locked_map_does_not_learn_a_name_it_already_knows():
    """The six rooms it wrongly invented were called 'A Vortex' and 'A Break
    in the Haze' -- names the map already had.  Those are recognition
    failures, and adding them makes the duplicate the lock exists to stop."""
    store, m = fresh()
    here = store.add_room("Somewhere")
    store.observe(here, ["n"], [])
    elsewhere = store.add_room("A Vortex")
    store.observe(elsewhere, ["e", "enter"], ["vortex"])
    store.locked = True
    m.arrived(["n"], [], name="Somewhere", at=0.0)

    m.sent("n", at=1.0)
    assert m.arrived(["s", "w"], ["haze"], name="A Vortex", at=1.1) is None
    assert store.db.execute("SELECT COUNT(*) c FROM room").fetchone()["c"] == 2


def test_a_look_that_answers_late_still_credits_the_step_that_moved_you():
    """'embrace void' teleports into the Tree of Life and sends no room block.
    By the time a look answers, the command has aged out of its window -- and
    it is the only thing that knows which of the two rooms called 'Doorway to
    a temple.' this is."""
    store, m = fresh()
    eastwick = store.add_room("Eastwick")
    doorway = store.add_room("Doorway to a temple.")
    twin = store.add_room("Doorway to a temple.")     # Tree of Life 1.0
    store.observe(eastwick, ["e", "w"], [])
    for room in (doorway, twin):
        store.observe(room, ["doorway", "leave"], [])
    store.link(eastwick, "embrace void", doorway)
    store.locked = True
    m.here = eastwick

    m.sent("embrace void", at=0.0)
    m.expect("embrace void", at=5.0)                  # the look, five seconds on
    assert m.arrived(["doorway", "leave"], [],
                     name="Doorway to a temple.", at=5.1) == doorway


def test_a_look_showing_the_same_room_means_the_step_did_nothing():
    store, m = fresh()
    here, there = store.add_room("Here"), store.add_room("There")
    store.observe(here, ["n"], ["sky"])
    store.observe(there, ["s"], ["road"])
    store.link(here, "n", there)
    m.arrived(["n"], ["sky"], at=0.0)
    m.here = here

    m.expect("n", at=5.0)
    assert m.arrived(["n"], ["sky"], at=5.1) == here   # we never left
    assert store.room(here)["visits"] == 1             # and it is not a visit


def test_walking_onto_an_identical_room_is_still_a_move():
    """A chessboard square looks exactly like the one you left.  Concluding
    'we did not move' from that would freeze the mapper on the board."""
    store, m = fresh()
    a = store.add_room("A Dark Square")
    b = store.add_room("A Light Square")
    for room in (a, b):
        store.observe(room, ["n", "s", "e", "w"], ["tiles"])
    store.link(a, "n", b)
    m.here = a

    m.sent("n", at=1.0)                                # a normal step, no look
    assert m.arrived(["n", "s", "e", "w"], ["tiles"], at=1.1) == b


def test_an_upgraded_area_is_told_apart_by_where_you_came_from():
    """3K keeps upgraded versions of areas alongside the originals -- Tree of
    Life and Tree of Life 2.0, Catacombs and Catacombs 2.  Fourteen of them
    leave 1,138 rooms indistinguishable by name and exits.  Both are real, so
    neither can be preferred; what can be is the one next door to the room we
    were last sure of."""
    store, m = fresh()
    eastwick = store.add_room("Eastwick")
    old = store.add_room("Doorway to a temple.")      # Tree of Life
    new = store.add_room("Doorway to a temple.")      # Tree of Life 2.0
    store.observe(eastwick, ["e", "w"], ["sky"])
    for room in (old, new):
        store.observe(room, ["doorway", "leave"], [])
    store.link(eastwick, "embrace void", new)         # only 2.0 is next door
    store.locked = True

    m.arrived(["e", "w"], ["sky"], at=0.0)
    assert m.here == eastwick
    m._was = eastwick
    m.here = None                                     # teleported, uncaused
    m._last_exits = ["doorway", "leave"]
    m.name_here("Doorway to a temple.")
    assert m.here == new


def test_a_tie_with_nothing_to_break_it_stays_a_tie():
    store, m = fresh()
    first, second = (store.add_room("A battleground"),
                     store.add_room("A battleground"))
    for room in (first, second):
        store.observe(room, ["n", "s"], ["mud"])
    assert m.arrived(["n", "s"], ["mud"], at=0.0) is None
    assert sorted(m.candidates) == sorted([first, second])


def test_a_block_that_opened_when_the_step_ran_is_still_its_answer():
    """A teleport does send a room block -- nothing settles it until the look
    three seconds later, so by the time it arrives it opened *before* the
    command was re-armed, and older than the attribution window allows.  The
    rule that a command cannot cause a block that predates it is right for
    ordinary traffic and wrong for exactly this."""
    store, m = fresh()
    eastwick = store.add_room("Eastwick")
    doorway = store.add_room("Doorway to a temple.")
    twin = store.add_room("Doorway to a temple.")
    store.observe(eastwick, ["e", "w"], ["sky"])
    for room in (doorway, twin):
        store.observe(room, ["doorway", "leave"], [])
    store.link(eastwick, "embrace void", doorway)
    store.locked = True
    m.here = eastwick

    m.sent("embrace void", at=59.8)
    m.expect("embrace void", at=62.8)        # the look, after the timeout
    # ...and the block it settles opened back when the teleport ran.
    assert m.arrived(["doorway", "leave"], [],
                     name="Doorway to a temple.", at=59.8) == doorway
    assert store.room(doorway)["visits"] == 1


def test_the_map_shows_the_area_you_are_in():
    """An area is what a person means by "where I am", and 3K's map has 777
    of them.  Spreading ten moves outward crossed into three at once and drew
    the links between them -- a great deal of ink about geography nobody was
    looking at."""
    store, m = fresh()
    here = store.add_region("Tree of Life 2.0")
    elsewhere = store.add_region("Chaos")
    doorway, temple = store.add_room("Doorway"), store.add_room("Temple")
    outside = store.add_room("Eastwick")
    store.assign([doorway, temple], here)
    store.assign([outside], elsewhere)
    store.link(doorway, "doorway", temple)
    store.link(doorway, "leave", outside)
    m.here = doorway

    view = m.neighbourhood()
    assert set(view["rooms"]) == {doorway, temple}
    assert m.neighbourhood(area_only=False)["rooms"].keys() >= {outside}


def test_a_room_with_no_area_still_shows_its_surroundings():
    """Which is what a map being built by hand looks like before anything has
    been labelled."""
    store, m = fresh()
    m.arrived(["e"], ["street"], at=0.0)
    first = m.here
    m.sent("e", at=1.0)
    m.arrived(["w"], ["hall"], at=1.1)
    assert set(m.neighbourhood()["rooms"]) == {first, m.here}



def test_a_locked_map_learns_a_way_out_nothing_told_it_about():
    """These are worth having and impossible to guess.  "embrace void" is an
    emote everywhere in 3K except one room in Eastwick, where it takes you to
    the Angels 2.0 area; "climb pipe" is how you get onto the chess board and
    "climb down" is how you leave it.  None is a direction, none is in DDD."""
    store, m = fresh()
    here = store.add_room("Eastwick")
    there = store.add_room("Doorway to a temple.")
    store.observe(here, ["n", "s"], ["cobbles"])
    store.observe(there, ["out"], ["pillars"])
    store.locked = True
    m.arrived(["n", "s"], ["cobbles"], name="Eastwick", at=0.0)

    m.sent("embrace void", at=1.0)
    landed = m.arrived(["out"], ["pillars"], name="Doorway to a temple.", at=1.1)
    assert store.destination(here, "embrace void") == landed


def test_no_command_leads_to_the_room_it_was_typed_in():
    """A block that says otherwise is a redisplay -- after a kill, or on the
    tick -- and the room it describes is the one we are standing in."""
    store, m = fresh()
    here = store.add_room("Palisade Pub")
    store.observe(here, ["n", "s"], ["bar"])
    store.locked = True
    m.arrived(["n", "s"], ["bar"], name="Palisade Pub", at=0.0)

    m.sent("wrap all", at=1.0)
    assert m.arrived(["n", "s"], ["bar"], name="Palisade Pub", at=1.1) == here
    assert store.exits_from(here) == [], "wrote an exit to itself"


def test_a_locked_map_does_not_grow_an_exit_it_was_only_guessing_at():
    """Six "wrap all" edges and a "disperse corpse" got written across the
    chess board when the housekeeping sent beside a step was blamed for it,
    and the panel then drew squares wherever those led -- rooms bleeding into
    a board that is a perfect eight by eight.

    A locked map is corrected, never grown, and that has to cover its edges.
    Nothing is lost: DDD lists every way out, and the edges that came with the
    map already carry the ones that are not directions."""
    store, m = fresh()
    here = store.add_room("A Light Square")
    there = store.add_room("A Dark Square")
    store.observe(here, ["n", "s", "e", "w"], ["tiles"])
    store.observe(there, ["n", "s", "e"], ["altar"])
    store.link(here, "w", there)
    store.locked = True
    m.arrived(["n", "s", "e", "w"], ["tiles"], name="A Light Square", at=0.0)

    m.sent("wrap all", at=1.0)
    landed = m.arrived(["n", "s", "e"], ["altar"], name="A Dark Square", at=1.1)

    assert landed == there, "it should still work out where it ended up"
    # the room can already get there by "w", so "wrap all" is the client
    # blaming the wrong one of several commands sent in the same breath
    assert store.destination(here, "wrap all") is None, "invented an exit"


def test_a_map_being_built_by_hand_still_learns_everything():
    """Unlocked, the only way it grows is by believing what it is told."""
    store, m = fresh()
    m.arrived(["n"], ["sky"], at=0.0)
    here = m.here
    m.sent("embrace void", at=1.0)
    landed = m.arrived(["out"], ["mist"], at=1.1)
    assert store.destination(here, "embrace void") == landed



def test_the_room_title_is_asked_first_when_lost():
    """The map has a name for every room and MIP sends one for every arrival.
    Exits and scenery are what is left when that fails, not the other way
    round: a name is worth more than a fingerprint two rooms can share."""
    store, m = fresh()
    chapel = store.add_room("The Chapel")
    barn = store.add_room("The Barn")
    for room in (chapel, barn):
        store.observe(room, ["n", "s"], ["floor"])   # identical fingerprints
    store.locked = True

    assert m.arrived(["n", "s"], ["floor"], at=0.0) is None, "should be unsure"
    assert m.arrived(["n", "s"], ["floor"], name="The Barn", at=1.0) == barn


def test_a_title_two_rooms_share_still_leaves_it_lost():
    """3K has sixty-four rooms called "A Dark Square" with the same four
    exits.  No map can say which one you are standing on; only walking can."""
    store, m = fresh()
    for _ in range(2):
        store.observe(store.add_room("A Dark Square"), ["n", "s", "e", "w"], [])
    store.locked = True
    assert m.arrived(["n", "s", "e", "w"], [], name="A Dark Square", at=0.0) is None
    assert len(m.candidates) == 2


def test_the_title_prefers_the_room_next_door():
    """Which is what tells Tree of Life from Tree of Life 2.0."""
    store, m = fresh()
    start = store.add_room("A road")
    near = store.add_room("The Tree of Life")
    far = store.add_room("The Tree of Life")
    for room in (near, far):
        store.observe(room, ["out"], [])
    store.observe(start, ["n"], [])
    store.link(start, "n", near)
    store.locked = True

    m.arrived(["n"], [], name="A road", at=0.0)
    m.here, m._was = None, start                 # something moved us
    assert m.arrived(["out"], [], name="The Tree of Life", at=1.0) == near
