"""Taking out exits the client invented while it was blaming the wrong command."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from mud.store import Store  # noqa: E402
from prune_edges import suspect  # noqa: E402


def board():
    """Two squares, joined west, as the imported map has them."""
    store = Store()
    here = store.add_room("A Light Square")
    there = store.add_room("A Dark Square")
    store.observe(here, ["n", "s", "e", "w"], ["tiles"])
    store.observe(there, ["n", "s", "e"], ["tiles"])
    store.link(here, "w", there)
    return store, here, there


def test_it_finds_an_exit_the_room_has_no_way_out_for():
    store, here, there = board()
    store.link(here, "wrap all", there)
    assert [e["command"] for e in suspect(store)] == ["wrap all"]


def test_it_leaves_alone_what_came_with_the_map():
    """tt++ stores speedwalks as edges on purpose -- ".gohome", "mines 1" --
    and they are not mistakes.  Nobody has walked them, which is how they are
    told apart."""
    store, here, there = board()
    store.db.execute(
        "INSERT INTO edge (from_room, command, to_room, seen, last_seen) "
        "VALUES (?, ?, ?, 0, 0)", (here, ".gohome", there))
    store.db.commit()
    assert suspect(store) == []


def test_it_leaves_a_direction_alone():
    """A room's recorded exits can be short -- tt++ truncates a long title at
    sixty characters, brackets and all -- so "e" missing from the list is a
    gap in the record rather than an invented exit."""
    store, here, there = board()
    store.link(here, "ne", there)                 # not in the room's exits
    assert suspect(store) == []


def test_a_direction_that_leads_back_to_itself_is_still_wrong():
    store, here, _there = board()
    store.link(here, "s", here)
    assert [e["command"] for e in suspect(store)] == ["s"]


def test_it_leaves_alone_a_way_out_the_room_does_list():
    store, here, there = board()
    store.observe(here, ["n", "s", "e", "w", "climb pipe"], ["tiles"])
    store.link(here, "climb pipe", there)
    assert suspect(store) == []


def test_one_command_can_be_singled_out():
    """"board cot" at the Academy landing pad is a real way to travel and
    belongs in the map; "wrap all" never is.  Both look the same from here, so
    the choosing is the reader's."""
    store, here, there = board()
    store.link(here, "wrap all", there)
    store.link(here, "board cot", there)
    assert len(suspect(store)) == 2
    assert [e["command"] for e in suspect(store, {"wrap all"})] == ["wrap all"]


def imported(store, room, command, to):
    """An edge that came with the map: nobody here has walked it."""
    store.db.execute(
        "INSERT INTO edge (from_room, command, to_room, seen, last_seen) "
        "VALUES (?, ?, ?, 0, 0)", (room, command, to))
    store.db.commit()


def test_it_finds_where_we_disagree_with_the_map_about_a_direction():
    """The importer walked 3K with tt++ and wrote down where "s" goes from the
    centre of Chaos.  A client blaming the wrong command for a room block
    wrote down somewhere else, and the router took it, because it was the
    shorter way to a place it does not go."""
    from prune_edges import disputed

    store, here, there = board()
    other = store.add_room("A road heading south")
    imported(store, here, "s", other)
    store.link(here, "s", there)                  # what we think we walked
    assert [e["to_room"] for e in disputed(store)] == [there]


def test_a_direction_the_map_agrees_with_is_left_alone():
    from prune_edges import disputed

    store, here, there = board()
    imported(store, here, "s", there)
    store.link(here, "s", there)
    assert disputed(store) == []


def test_a_command_the_map_never_had_is_not_a_disagreement():
    """It is a way out nobody told the map about, which is the other check."""
    from prune_edges import disputed

    store, here, there = board()
    store.link(here, "embrace void", there)
    assert disputed(store) == []
