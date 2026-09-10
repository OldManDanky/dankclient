"""Rooms tt++ never named, and rooms that are not rooms at all.

The importer threw away every room without a name as "an unused room
number".  3,478 of them had exits.  1,253 were tt++'s *void* rooms -- spacers
for drawing a long way between two rooms, which a player walks straight
through -- and 2,225 were real rooms tt++ passed without catching a title.
Between them they were the only ways into whole areas: Xenolocles by way of
Ravenloft, Westersea, the Underdark.  A quarter of the speedruns could not be
reached from anywhere.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.tintin import import_map  # noqa: E402


def room(vnum, name="", flags=0, area="Here"):
    return (f"R {{{vnum}}} {{{flags}}} {{}} {{{name}}} {{ }} {{}} {{{area}}} "
            "{} {} {} {1.000} {}")


def exit_(to, name, command=""):
    return f"E {{{to}}} {{{name}}} {{{command}}} {{0}} {{0}} {{}} {{1.000}} {{}} {{0.00}}"


def load(lines, store=None, merge=False):
    path = Path(tempfile.mkdtemp()) / "test.map"
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    store = store or Store()
    return store, import_map(store, path, merge=merge)


#: Town (1) --e--> a spacer (50) --e--> another spacer (51) --e--> Gate (2),
#: and Gate --n--> a room tt++ never named (3) --n--> Keep (4).  Plus a
#: spacer that forks (60), a number nobody used (70), and the way back.
MAP = [
    room(1, "Town (e)"), exit_(50, "e"),
    room(50, flags=8), exit_(1, "w"), exit_(51, "e"),
    room(51, flags=8), exit_(50, "w"), exit_(2, "e"),
    room(2, "Gate (n,w)"), exit_(3, "n"), exit_(51, "w"), exit_(60, "s"),
    room(3), exit_(4, "n"), exit_(2, "s"),
    room(4, "Keep (s)"), exit_(3, "s"),
    room(60, flags=8), exit_(2, "n"), exit_(1, "e"), exit_(4, "w"),
    room(70),
]


def test_a_way_through_spacers_leads_where_they_end():
    store, did = load(MAP)
    assert store.destination(1, "e") == 2, "Town east is the Gate, spacers and all"
    assert store.destination(2, "w") == 1, "and back"
    assert store.room(50) is None and store.room(51) is None, "not rooms"
    assert did["voids"] == 2


def test_a_spacer_that_forks_is_not_a_corridor():
    store, did = load(MAP)
    assert store.destination(2, "s") is None


def test_a_room_with_no_name_but_a_way_out_is_a_room():
    store, did = load(MAP)
    assert store.room(3) is not None and store.room(3)["name"] is None
    assert store.destination(2, "n") == 3 and store.destination(3, "n") == 4
    exits = store.db.execute("SELECT exits FROM fingerprint WHERE room_id = 3"
                             ).fetchone()["exits"]
    assert exits == "n,s", "its exits taken from its edges, so it can be checked"
    assert did["unnamed"] == 1


def test_a_number_nobody_used_is_still_skipped():
    store, did = load(MAP)
    assert store.room(70) is None and did["blank"] == 1


def test_the_keep_is_reachable_through_all_of_it():
    store, did = load(MAP)
    m = Mapper(store)
    m.here = 1
    assert m.route(4) == ["e", "n", "n"]


def test_an_update_adds_them_to_a_map_already_played_on():
    """What Options -> Updates does with the fixed importer: only adds."""
    old = [line for line in MAP if not line.startswith("R {3}")]
    store, _ = load([room(1, "Town (e)"), room(2, "Gate (n,w)"), room(4, "Keep (s)")])
    store.rename(2, "The Gate, as renamed")
    load(MAP, store, merge=True)
    assert store.destination(1, "e") == 2 and store.room(3) is not None
    assert store.room(2)["name"] == "The Gate, as renamed", "a merge keeps names"
    assert old  # (the fixture without room 3 is what an old import looked like)


def test_the_map_importer_is_marked_as_changed():
    from mud import update
    assert update.IMPORTERS["map"] >= 2, "or nobody who already pulled gets the rooms"
