"""Reading a TinTin++ map.  Player's is 49,494 rooms and 154,073 exits, so
the parser meets nesting, blank room numbers and exits leading nowhere."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.tintin import fields, import_map, import_speedruns  # noqa: E402

# Lifted verbatim from 3k_shared.map, trimmed to fit.
SAMPLE = """C 99999

V 20231

R {1}{0}{<278>}{The Center of Town (d,n,s,e)}{-+-}{This is the center of \
Pinnacle.}{Pinnacle}{cot}{}{}{1.000}{1}
E {2}{e}{e}{2}{0}{}{1.000}{}{0.00}
E {6}{n}{n}{1}{0}{}{1.000}{}{0.00}
E {63}{d}{d}{0}{0}{}{1.000}{}{0.00}
E {9999}{s}{s}{0}{0}{}{1.000}{}{0.00}
R {2}{0}{<138>}{The Trading Post (w)}{*$*}{A shop.}{Pinnacle}{shop}{}\
{{mobs} {Cancer}}{1.000}{1}
E {1}{w}{w}{2}{0}{}{1.000}{}{0.00}
R {3}{0}{<118>}{}{ }{}{}{}{}{}{1.000}{}
R {6}{0}{<118>}{North of Center (s)}{|}{A street.}{Pinnacle}{}{}{}{1.000}{1}
E {1}{s}{s}{0}{0}{}{1.000}{}{0.00}
R {63}{0}{<118>}{A cellar (u)}{|}{Dark.}{Cellars}{}{}{}{1.000}{1}
E {1}{u}{lift grate;u}{0}{0}{}{1.000}{}{0.00}
"""

SPEEDRUNS = """
#alias .add_speedrun {
    #list speedruns_name add {%1};
};

.add_speedrun {cot} {area} {1} {Pinnacle: Center of Town};
.add_speedrun {shop} {shop} {2} {The Trading Post};
.add_speedrun {gone} {mob} {77777} {A room the map no longer has};
"""


def loaded():
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "3k.map"
    path.write_text(SAMPLE)
    store = Store()
    result = import_map(store, path)
    return tmp, store, path, result


# --- the field parser ---------------------------------------------------------


def test_fields_are_read_by_depth_not_by_splitting():
    """The room data field holds {{mobs} {Cancer}}, so a split on braces
    would shear it in half."""
    assert fields("{1}{0}{a}{{mobs} {Cancer}}{x}") == [
        "1", "0", "a", "{mobs} {Cancer}", "x"
    ]


def test_an_empty_field_stays_a_field():
    assert fields("{1}{}{b}") == ["1", "", "b"]


# --- the map ------------------------------------------------------------------


def test_room_numbers_are_kept_as_room_ids():
    """The speedrun list refers to rooms by number and so does everything
    Player has written; renumbering would throw that away for nothing."""
    tmp, store, _, _ = loaded()
    assert store.room(1)["name"] == "The Center of Town"
    assert store.room(2)["name"] == "The Trading Post"
    tmp.cleanup()


def test_the_exits_in_the_title_become_the_rooms_fingerprint():
    """tt++ writes them into the room name, and they are the same list DDD
    sends -- so dead reckoning can check itself from the first step."""
    tmp, store, _, _ = loaded()
    assert store.exits_of(1) == ["d", "e", "n", "s"]
    assert store.consistent(1, ["d", "e", "n", "s"], [])
    tmp.cleanup()


def test_areas_become_regions():
    tmp, store, _, result = loaded()
    assert result["areas"] == 2
    assert store.region_path(1) == ["Pinnacle"]
    assert store.region_path(63) == ["Cellars"]
    tmp.cleanup()


def test_the_speedwalk_note_is_kept():
    tmp, store, _, _ = loaded()
    assert store.room(1)["note"] == "cot"
    tmp.cleanup()


def test_a_room_number_with_no_name_is_skipped():
    """Five thousand of them are simply unused."""
    tmp, store, _, result = loaded()
    assert store.room(3) is None
    assert result["blank"] == 1
    tmp.cleanup()


def test_an_exit_to_a_room_that_does_not_exist_is_dropped():
    """Three thousand of Player's lead nowhere.  A dangling edge would make
    routing offer paths that cannot be walked."""
    tmp, store, _, result = loaded()
    assert store.destination(1, "s") is None
    assert result["dangling"] == 1
    tmp.cleanup()


def test_the_command_is_taken_over_the_direction():
    """'lift grate;u' is how you go up from the cellar."""
    tmp, store, _, _ = loaded()
    assert store.destination(63, "lift grate;u") == 1
    tmp.cleanup()


# --- routing over what was imported -------------------------------------------


def test_routing_prefers_walking_to_somebody_elses_alias():
    """An imported map is full of shortcuts.  Counting every exit as one step
    finds routes that are shortest and useless."""
    store = Store()
    a, b, c = store.add_room("A"), store.add_room("B"), store.add_room("C")
    store.link(a, ".gohome", c)              # one step, but a tt++ alias
    store.link(a, "n", b)
    store.link(b, "e", c)
    m = Mapper(store)
    assert m.route(c, start=a) == ["n", "e"]


def test_a_multi_command_exit_costs_more_than_a_step():
    assert Mapper.cost("n") < Mapper.cost("enter") < Mapper.cost("lift grate;d")
    assert Mapper.cost("lift grate;d") < Mapper.cost(".gohome")


# --- landmarks ----------------------------------------------------------------


def test_speedruns_become_landmarks_and_missing_ones_are_reported():
    tmp, store, path, _ = loaded()
    marks = path.with_name("speedruns.tin")
    marks.write_text(SPEEDRUNS)

    added, missing = import_speedruns(store, marks)
    assert added == 2 and missing == ["gone"]
    assert store.landmark("cot")["room_id"] == 1
    assert [m["name"] for m in store.landmarks("trading")] == ["shop"]
    tmp.cleanup()


# --- finding yourself in a world you have never walked ------------------------


def test_being_named_a_room_is_enough_when_the_name_is_unique():
    """An imported map is a world with no idea where you are in it.  MIP names
    the room on the tick, and a third of 3K's rooms are unique on name and
    exits together."""
    tmp, store, _, _ = loaded()
    m = Mapper(store)
    m.arrived(["d", "e", "n", "s"], [], at=0.0)
    m.here = None                            # the arrival made its own room
    m._last_exits = ["d", "e", "n", "s"]
    m.name_here("The Center of Town")
    assert m.here == 1
    tmp.cleanup()


def test_an_ambiguous_name_leaves_candidates_to_narrow():
    store = Store()
    for _ in range(3):
        room = store.add_room("A battleground")
        store.observe(room, ["n", "s"], [])
    m = Mapper(store)
    m._last_exits = ["n", "s"]
    m.name_here("A battleground")
    assert m.here is None
    assert len(m.candidates) == 3


# --- pulling in a map that has grown -----------------------------------------

GROWN = SAMPLE + (
    "R {77}{0}{<118>}{A New Cavern (n)}{|}{Fresh.}{Underdark}{}{}{}{1.000}{1}\n"
    "E {1}{n}{n}{0}{0}{}{1.000}{}{0.00}\n"
)


def played_on():
    """A map imported, then played on: walked, corrected, learned from."""
    tmp = tempfile.TemporaryDirectory()
    first, again = Path(tmp.name) / "3k.map", Path(tmp.name) / "grown.map"
    first.write_text(SAMPLE)
    again.write_text(GROWN)
    store = Store()
    import_map(store, first)
    store.db.execute("UPDATE room SET visits = 42 WHERE id = 1")
    store.rename(2, "The Trading Post -- Ada sells rope here")
    store.observe(1, ["d", "n", "s", "e"], ["fountain"])
    store.link(1, "climb pipe", 63, 0.0)
    return store, again, tmp


def test_a_merge_brings_in_what_the_map_has_grown():
    store, again, _tmp = played_on()
    import_map(store, again, merge=True)
    assert store.room(77)["name"] == "A New Cavern"
    assert store.destination(1, "n") in (6, 77)


def test_a_merge_costs_you_nothing_you_had():
    """Measured before this existed: a second import duplicated every region,
    reset every visit count to zero, wiped every fingerprint the client had
    learned by walking, marked every walked edge unwalked, and put a room the
    player had renamed by hand back to the name tt++ gave it."""
    store, again, _tmp = played_on()
    one = lambda q: store.db.execute(q).fetchone()[0]  # noqa: E731

    import_map(store, again, merge=True)

    assert one("SELECT visits FROM room WHERE id = 1") == 42
    assert one("SELECT name FROM room WHERE id = 2") \
        == "The Trading Post -- Ada sells rope here"
    assert one("SELECT count(*) FROM fingerprint WHERE seen > 0") == 1
    assert one("SELECT count(*) FROM edge WHERE seen > 0") == 1


def test_a_merge_does_not_give_you_two_of_every_area():
    """Regions were made on the way past rather than looked up, so the second
    import gave the map a second Pinnacle and split the rooms between them."""
    store, again, _tmp = played_on()
    before = store.db.execute("SELECT count(*) FROM region").fetchone()[0]
    import_map(store, again, merge=True)
    after = store.db.execute(
        "SELECT count(*) FROM region").fetchone()[0]
    assert after == before + 1, "one new area, not a copy of every old one"
    assert len(store.db.execute(
        "SELECT id FROM region WHERE name = 'Pinnacle'").fetchall()) == 1


def test_a_first_import_still_owns_the_database():
    """The merge is the careful path, not a replacement for the plain one:
    importing into an empty map should not have to tiptoe."""
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "3k.map"
    path.write_text(SAMPLE)
    store = Store()
    got = import_map(store, path)
    assert got["rooms"] == 4 and got["edges"] > 0


# --- tt++ talking to itself --------------------------------------------------

def test_a_client_directive_is_not_a_way_to_move():
    """`#map goto $puddle_room` moves tt++'s own cursor. Typed at 3K it means
    nothing and still spends a command against the rate the MUD watches."""
    from mud.tintin import walkable

    assert walkable("follow bubbles;u;#delay 0.5 #map goto $puddle_room") \
        == "follow bubbles;u"
    assert walkable("out;#map at 24786 {#map link {unpause game}}") == "out"
    assert walkable("#map goto $ashridge_room") == ""


def test_a_repeat_count_keeps_the_command_inside_it():
    """439 of the 472 directives in Player's map are #map and go; 24 are
    "#4 turn left dial", where the number is a repeat and the rest is real.
    Dropping anything with a hash in it would throw those away."""
    from mud.tintin import walkable

    assert walkable("#3 turn left dial") \
        == "turn left dial;turn left dial;turn left dial"
    assert walkable("#2 {smash brick}; w") == "smash brick;smash brick;w"
    assert walkable("#send forge") == "forge"


def test_a_repeat_cannot_empty_the_rate_limiter():
    from mud.tintin import walkable, MOST_REPEATS

    assert walkable("#9999 climb").split(";") == ["climb"] * MOST_REPEATS


def test_exits_are_cleaned_on_the_way_in():
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "3k.map"
    path.write_text(SAMPLE + (
        "R {88}{0}{<118>}{A Dial Room (n)}{|}{Dials.}{Pinnacle}{}{}{}{1.000}{1}\n"
        "E {1}{n}{#2 turn dial;#map goto $cot;n}{0}{0}{}{1.000}{}{0.00}\n"))
    store = Store()
    import_map(store, path)
    got = [e["command"] for e in store.exits_from(88)]
    assert got == ["turn dial;turn dial;n"], got


def test_a_map_that_already_has_them_is_cleaned_too():
    """A map imported before the importer knew to strip these keeps 469 of
    them, and every one is a command the client would type into the game."""
    from mud.tintin import walkable

    store = Store()
    store.add_room("A Dial Room")
    store.add_room("Somewhere Else")
    store.link(1, "#31 climb", 2, 0.0)
    store.link(1, "#31 climb;", 2, 0.0)      # cleans to the same thing
    store.link(1, "#map goto $cot", 2, 0.0)  # cleans to nothing at all

    assert store.clean_edge_commands(walkable) == 3
    left = sorted(e["command"] for e in store.exits_from(1))
    assert left == [";".join(["climb"] * 31)], left


def test_an_exit_with_no_directive_is_left_exactly_as_it_is():
    """A filter, not a formatter. tt++ writes "search;open trapdoor; stairs"
    with a space, and rebuilding the string without it makes a second exit
    beside the first -- the same way out of the same room, twice. 136 of them,
    found by checking a live map after an update rather than by reading code."""
    from mud.tintin import walkable

    for command in ("search;open trapdoor; stairs", "punch steps; climb tank",
                    "n", "steps\;", "buy ticket;enter"):
        assert walkable(command) == command, command


def test_the_same_way_out_written_twice_is_folded():
    store = Store()
    store.add_room("The Chapel")
    store.add_room("A Cellar")
    store.link(1, "search;open trapdoor; stairs", 2, 0.0)
    store.link(1, "search;open trapdoor;stairs", 2, 0.0)
    store.link(1, "d", 2, 0.0)

    assert store.fold_spaced_exits() == 1
    left = sorted(e["command"] for e in store.exits_from(1))
    # the longer spelling survives: it is the one tt++ wrote
    assert left == ["d", "search;open trapdoor; stairs"], left


def test_folding_keeps_the_one_you_have_walked():
    """That is the one carrying evidence -- the seen count and the failures."""
    store = Store()
    store.add_room("The Chapel")
    store.add_room("A Cellar")
    store.link(1, "punch steps;climb tank", 2, 0.0)   # short, but walked
    store.link(1, "punch steps; climb tank", 2, 0.0)
    store.db.execute("UPDATE edge SET seen = 9 WHERE command = ?",
                     ("punch steps;climb tank",))

    assert store.fold_spaced_exits() == 1
    assert [e["command"] for e in store.exits_from(1)] == ["punch steps;climb tank"]
