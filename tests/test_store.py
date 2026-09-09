"""The store holds the map and the log.  These tests pin the three rules the
schema exists to enforce, each of which was a wrong guess first."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.store import SCHEMA_VERSION, Store  # noqa: E402


def test_it_opens_a_new_file_and_reopens_it():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "maps" / "3k.sqlite"      # directory does not exist
        with Store(path) as s:
            room = s.add_room("The Center of Town")
        with Store(path) as s:
            assert s.room(room)["name"] == "The Center of Town"


def test_a_newer_schema_is_refused_rather_than_mangled():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "3k.sqlite"
        Store(path).close()
        db = sqlite3.connect(path)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        db.close()
        try:
            Store(path)
        except RuntimeError as err:
            assert "schema" in str(err)
        else:
            raise AssertionError("opened a database it does not understand")


# --- fingerprints -------------------------------------------------------------


def test_scenery_that_drifts_still_matches_the_room():
    """'A Light Square' was seen with and without 'litter' -- someone had
    dropped something.  Equality would call that a different room."""
    s = Store()
    room = s.add_room("A Light Square")
    s.observe(room, "n s e w".split(), "area brush flames light litter sky".split())
    hits = s.candidates("n s e w".split(), "area brush flames light sky".split())
    assert hits and hits[0][0] == room
    assert 0.5 < hits[0][1] < 1.0                # close, and honest about it


def test_exits_must_match_because_the_mud_computes_them():
    s = Store()
    room = s.add_room()
    s.observe(room, ["n", "s"], ["sky"])
    assert s.candidates(["n", "s", "e"], ["sky"]) == []


def test_every_variant_is_kept_and_counted():
    s = Store()
    room = s.add_room()
    s.observe(room, ["n"], ["sky"])
    s.observe(room, ["n"], ["sky"])
    s.observe(room, ["n"], ["sky", "rain"])      # weather turned up
    rows = s.db.execute(
        "SELECT scenery, seen FROM fingerprint WHERE room_id = ? ORDER BY seen DESC",
        (room,),
    ).fetchall()
    assert [(r["scenery"], r["seen"]) for r in rows] == [("sky", 2), ("rain,sky", 1)]


def test_the_chessboard_is_ambiguous_and_says_so():
    """Two squares with the same exits and the same scenery: the store must
    offer both rather than picking one, or the map silently goes wrong."""
    s = Store()
    dark, light = s.add_room("A Dark Square"), s.add_room("A Light Square")
    for room in (dark, light):
        s.observe(room, "n s e w".split(), ["tiles"])
    hits = s.candidates("n s e w".split(), ["tiles"])
    assert sorted(r for r, _ in hits) == [dark, light]
    assert {score for _, score in hits} == {1.0}


# --- edges --------------------------------------------------------------------


def test_a_command_may_have_more_than_one_destination():
    """Random exits exist.  Keying edges by (from, command) alone would make
    each traversal quietly overwrite the last."""
    s = Store()
    here, a, b = s.add_room(), s.add_room(), s.add_room()
    s.link(here, "enter", a)
    s.link(here, "enter", b)
    s.link(here, "enter", b)
    assert s.destination(here, "enter") == b          # likeliest, by count
    assert {r["to_room"] for r in s.exits_from(here)} == {a, b}


def test_multi_word_commands_are_edges_like_any_other():
    """'climb pipe' moves you and appears in no exit list."""
    s = Store()
    street, board = s.add_room(), s.add_room("A Dark Square")
    s.link(street, "Climb Pipe", board)
    assert s.destination(street, "climb pipe") == board


# --- names --------------------------------------------------------------------


def test_a_visit_fills_a_blank_name_but_does_not_overwrite_one():
    s = Store()
    room = s.add_room()
    s.visit(room, "North lane")
    s.visit(room, None)
    s.visit(room, "Somewhere else")
    assert s.room(room)["name"] == "North lane"
    assert s.room(room)["visits"] == 3


# --- regions ------------------------------------------------------------------


def test_region_path_reads_outermost_first():
    s = Store()
    chaos = s.add_region("Chaos")
    tree = s.add_region("Tree of Life", parent_id=chaos)
    room = s.add_room("Temple of Malkuth")
    s.assign([room], tree)
    assert s.region_path(room) == ["Chaos", "Tree of Life"]


def test_a_region_cycle_does_not_hang():
    s = Store()
    a = s.add_region("A")
    b = s.add_region("B", parent_id=a)
    s.db.execute("UPDATE region SET parent_id = ? WHERE id = ?", (b, a))
    room = s.add_room()
    s.assign([room], b)
    assert sorted(s.region_path(room)) == ["A", "B"]


def test_deleting_a_region_leaves_its_rooms_alone():
    s = Store()
    region = s.add_region("Eastwick")
    room = s.add_room("Eastwick Road")
    s.assign([room], region)
    s.db.execute("DELETE FROM region WHERE id = ?", (region,))
    assert s.room(room) is not None
    assert s.room(room)["region_id"] is None


# --- the log ------------------------------------------------------------------


def test_search_finds_a_line_and_can_narrow_by_kind():
    s = Store()
    sid = s.begin_session()
    s.log(sid, "chat", "[Clan] Player : moo", channel="Clan Sa", who="Player")
    s.log(sid, "recv", "Player shouts: BIG MOO")
    s.log(sid, "sent", "shout BIG MOO")
    assert len(s.search("moo")) == 3
    assert [r["kind"] for r in s.search("moo", kind="sent")] == ["sent"]


def test_a_malformed_query_searches_instead_of_throwing():
    """FTS5 syntax is its own language; a search box must not raise on it."""
    s = Store()
    sid = s.begin_session()
    s.log(sid, "recv", 'he said "belochs" loudly')
    assert len(s.search('"belochs')) == 1
    assert s.search("NEAR") == []


def test_lines_can_be_found_by_where_you_were_standing():
    s = Store()
    sid, room = s.begin_session(), s.add_room("Temple of Hod")
    s.log(sid, "recv", "Michael raises his arms", room_id=room)
    s.log(sid, "recv", "Michael raises his arms")
    assert len(s.search("Michael", room_id=room)) == 1


def test_context_returns_the_lines_around_a_hit():
    s = Store()
    sid = s.begin_session()
    ids = [s.log(sid, "recv", f"line {i}") for i in range(10)]
    got = [r["text"] for r in s.context(ids[5], before=2, after=2)]
    assert got == ["line 3", "line 4", "line 5", "line 6", "line 7"]


def test_context_at_the_very_start_does_not_run_off_the_end():
    s = Store()
    sid = s.begin_session()
    ids = [s.log(sid, "recv", f"line {i}") for i in range(3)]
    assert [r["text"] for r in s.context(ids[0], before=5, after=5)] == [
        "line 0", "line 1", "line 2"
    ]


# --- correcting the map -------------------------------------------------------


def test_merging_two_halves_of_one_room_keeps_every_way_in_and_out():
    """A missed move splits one room in two and nothing rejoins them: to the
    map they are simply two places.  Merging has to carry the edges."""
    s = Store()
    north, keep, drop, south = (s.add_room("North"), s.add_room("Hall"),
                                s.add_room(), s.add_room("South"))
    s.link(north, "s", keep)
    s.link(drop, "s", south)
    s.link(south, "n", drop)

    s.merge(keep, drop)

    assert s.room(drop) is None
    assert s.destination(keep, "s") == south
    assert s.destination(south, "n") == keep
    assert s.destination(north, "s") == keep


def test_merging_drops_the_self_loop_it_creates():
    """The two halves usually lead to each other, and a room does not have an
    exit to itself."""
    s = Store()
    keep, drop = s.add_room("Hall"), s.add_room()
    s.link(keep, "n", drop)
    s.link(drop, "s", keep)
    s.merge(keep, drop)
    assert s.exits_from(keep) == []


def test_merging_keeps_the_name_and_the_history():
    s = Store()
    keep, drop = s.add_room(), s.add_room("Alchemy row")
    sid = s.begin_session()
    s.log(sid, "recv", "something happened", room_id=drop)
    s.visit(keep)
    s.visit(drop)

    s.merge(keep, drop)
    assert s.room(keep)["name"] == "Alchemy row"
    assert s.room(keep)["visits"] == 2
    assert s.search("something")[0]["room_id"] == keep


def test_a_room_can_be_renamed_or_unnamed():
    s = Store()
    room = s.add_room("Wrong")
    s.rename(room, "Right")
    assert s.room(room)["name"] == "Right"
    s.rename(room, None)
    assert s.room(room)["name"] is None
    s.suggest_name(room, "North lane")        # blank again, so this sticks
    assert s.room(room)["name"] == "North lane"


def test_duplicates_are_suggested_but_never_acted_on():
    """3K really does have two Alchemy rows, so this proposes and a person
    decides.  Rooms with no scenery are left out: with nothing to compare,
    every bare corridor would look like every other."""
    s = Store()
    a, b, other = s.add_room("A Vortex"), s.add_room("A Vortex"), s.add_room()
    for room in (a, b):
        s.observe(room, ["e", "enter"], ["vortex", "sky"])
    s.observe(other, ["e", "enter"], [])
    bare = s.add_room()
    s.observe(bare, ["e", "enter"], [])

    groups = s.duplicates()
    assert len(groups) == 1
    assert sorted(groups[0][1]) == sorted([a, b])


def test_repair_drops_a_one_off_reading_that_contradicts_a_room():
    """A room's exits do not change.  One exit list seen once against a dozen
    is another room's block written onto this one."""
    s = Store()
    room = s.add_room("A Break in the Haze")
    for _ in range(12):
        s.observe(room, ["e", "n", "w"], ["bricks", "haze"])
    s.observe(room, ["e", "enter", "s", "w"], ["vortex"])   # the stray

    assert s.prune_fingerprints() == [(room, "e,enter,s,w")]
    assert s.exits_of(room) == ["e", "n", "w"]
    assert not s.consistent(room, ["e", "enter", "s", "w"], ["vortex"])


def test_repair_leaves_a_genuinely_contested_room_alone():
    """Two readings of comparable weight are a question, not a mistake."""
    s = Store()
    room = s.add_room()
    for _ in range(6):
        s.observe(room, ["n"], ["sky"])
    for _ in range(5):
        s.observe(room, ["n", "s"], ["sky"])
    assert s.prune_fingerprints() == []


def test_exits_are_backfilled_from_the_edges():
    """tt++ leaves the exits out of some room titles -- 5.2% of the real map
    -- but the ways out were mapped all the same.  Without this those rooms
    can never match a live one, since MIP's exit list will not equal []."""
    s = Store()
    room, other = s.add_room("A Break in the Haze"), s.add_room()
    s.observe(room, [], [])                  # a title with no (exits)
    for direction in ("e", "n", "w"):
        s.link(room, direction, other)

    assert s.backfill_exits() == 1
    assert s.exits_of(room) == ["e", "n", "w"]
    assert s.consistent(room, ["e", "n", "w"], [])


def test_backfill_leaves_a_room_that_already_has_exits_alone():
    s = Store()
    room, other = s.add_room(), s.add_room()
    s.observe(room, ["n", "s"], ["sky"])
    s.link(room, "e", other)
    assert s.backfill_exits() == 0
    assert s.exits_of(room) == ["n", "s"]


def test_a_room_may_hold_more_ways_out_than_it_lists():
    """The Chapel's map entry knows about its stairs and its trapdoor; DDD
    reports only the door west.  Demanding equality made the room the map
    definitely had look like one it did not."""
    s = Store()
    chapel = s.add_room("The Chapel of the Three Kingdoms")
    hall, cellar = s.add_room(), s.add_room()
    s.observe(chapel, ["w", "stairs"], ["pews"])
    s.link(chapel, "w", hall)
    s.link(chapel, "stairs", cellar)

    assert s.consistent(chapel, ["w"], ["pews"])          # a subset of its ways out
    assert not s.consistent(chapel, ["n"], ["pews"])      # not one of them
    # Identifying a room out of nowhere is still strict.
    assert s.candidates(["w"], ["pews"]) == []


def test_backfill_ignores_a_macro_recorded_as_an_exit():
    """'search;open trapdoor; stairs' is a way to leave a room, not an exit it
    lists, and DDD will never report it."""
    s = Store()
    room, other = s.add_room("The Chapel"), s.add_room()
    s.observe(room, [], [])
    s.link(room, "w", other)
    s.link(room, "search;open trapdoor; stairs", other)
    s.backfill_exits()
    assert s.exits_of(room) == ["w"]


def test_a_macro_is_taken_back_out_of_a_rooms_exits():
    """An earlier backfill took exits from edges without asking whether they
    were exits.  A room carrying one can still be recognised -- checking
    accepts a subset -- but never identified from a standing start, because
    that comparison is exact."""
    s = Store()
    room = s.add_room("A cave")
    s.db.execute(
        "INSERT INTO fingerprint (room_id, exits, scenery, seen, last_seen) "
        "VALUES (?,?,?,1,0)", (room, "#15 hack east; east;,cave,e", "rock"))

    assert s.candidates(["cave", "e"], ["rock"]) == []
    assert s.clean_exits() == 1
    assert s.exits_of(room) == ["cave", "e"]
    assert [r for r, _ in s.candidates(["cave", "e"], ["rock"])] == [room]
