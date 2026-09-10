"""Somebody's house is not a way out of a public room.

3kdb's map was walked by one player, and every `home` in it goes to his
house.  Seventeen public rooms led there, and before this 57 of 259 routes
between rooms around Pinnacle went in through his door and out through his
house's portal -- which works for nobody else.  Measured on a real map, not
imagined: the rooms only reachable by going home were his house, eight other
particular houses by number, and one clan's hall.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store, personal  # noqa: E402
from mud.tintin import import_map  # noqa: E402

#: A public square with a shop to the east, and a house reachable from the
#: square by `home`, by one house's number, and by a tt++ alias.  The house's
#: portal room has a shortcut to the shop, which is the trap: it makes going
#: home look like the fastest way anywhere.
SAMPLE = """\
R {1}{0}{<278>}{The Square (e)}{-+-}{A square.}{Town}{}{}{}{1.000}{}
E {2}{e}{e}{0}{0}{}{1.000}{}{0.00}
E {10}{home}{home}{0}{0}{}{1.000}{}{0.00}
E {10}{home 726}{home 726}{0}{0}{}{1.000}{}{0.00}
E {10}{u}{.goHome}{0}{0}{}{1.000}{}{0.00}
R {2}{0}{<138>}{The Far Shop (w)}{*$*}{A shop.}{Town}{}{}{}{1.000}{}
E {3}{w}{w}{0}{0}{}{1.000}{}{0.00}
R {3}{0}{<138>}{A Long Road (e,w)}{-}{A road.}{Town}{}{}{}{1.000}{}
E {1}{w}{w}{0}{0}{}{1.000}{}{0.00}
E {2}{e}{e}{0}{0}{}{1.000}{}{0.00}
R {10}{0}{<138>}{Somebody's Portal Room (shop)}{-}{A house.}{House}{}{}{}{1.000}{}
E {2}{shop}{shop}{0}{0}{}{1.000}{}{0.00}
"""


def imported() -> Store:
    path = Path(tempfile.mkdtemp()) / "sample.map"
    path.write_text(SAMPLE)
    store = Store()
    import_map(store, path)
    return store


def commands(store: Store) -> set[str]:
    return {r["command"] for r in store.db.execute("SELECT command FROM edge")}


def test_which_commands_go_home():
    for yes in ("home", "Home", " home ", "home 726", "home  134", ".goHome",
                ".gohome"):
        assert personal(yes), yes
    for no in ("n", "homeward", "house", "enter home", "home sweet", "gohome",
               "home726", "shop"):
        assert not personal(no), no


def test_somebody_elses_aliases_are_not_ways_out_either():
    """`.fly` and `.land` were his tt++ aliases, and the only way the map had
    into Mystic Seal.  Typed at 3K, they do nothing."""
    for yes in (".fly;u", ".land;n", ".fly;climb cliff", "x;.land;e"):
        assert personal(yes), yes
    for no in ("fly", "land", "search;open trapdoor; stairs", "say ...", "n.e"):
        assert not personal(no), no


def test_the_importer_leaves_them_out():
    got = commands(imported())
    assert not {"home", "home 726", ".gohome"} & got
    assert {"e", "w", "shop"} <= got


def test_the_house_is_still_there_but_nobody_is_routed_into_it():
    """The rooms are not wrong -- only the claim that anybody can walk in."""
    store = imported()
    assert store.db.execute("SELECT 1 FROM room WHERE id = 10").fetchone()
    m = Mapper(store)
    m.here = 1
    assert m.route(10) is None
    assert m.route(2) == ["e"]


def test_a_map_that_already_has_them_is_cleaned_once():
    path = Path(tempfile.mkdtemp()) / "map.sqlite"
    with Store(path) as store:
        now = 0.0
        for rid in (1, 2, 10):
            store.db.execute("INSERT INTO room (id, name, first_seen, last_seen) "
                             "VALUES (?,?,?,?)", (rid, f"r{rid}", now, now))
        for cmd, to in (("home", 10), ("home 726", 10), (".gohome", 10),
                        ("e", 2)):
            store.db.execute("INSERT INTO edge (from_room, command, to_room, "
                             "last_seen) VALUES (1,?,?,0)", (cmd, to))
        # As a map from before this existed: never cleaned.
        store.db.execute("DELETE FROM meta WHERE key = 'forgot:personal'")
    with Store(path) as store:
        assert commands(store) == {"e"}
        assert store.setting("forgot:personal") == "1"


def test_one_that_comes_back_is_still_not_routed_through():
    """An older client merging an older map could put them back."""
    store = imported()
    store.db.execute("INSERT INTO edge (from_room, command, to_room, last_seen) "
                     "VALUES (1, 'home', 10, 0)")
    m = Mapper(store)
    m.here = 1
    assert m.route(2) == ["e"], "not home, then the portal's shop"


def test_walking_home_does_not_teach_the_map_where_home_is():
    store = Store()
    now = 0.0
    for rid in (1, 10):
        store.db.execute("INSERT INTO room (id, name, first_seen, last_seen) "
                         "VALUES (?,?,?,?)", (rid, f"r{rid}", now, now))
    store.link(1, "home", 10, now)
    assert "home" not in commands(store)
