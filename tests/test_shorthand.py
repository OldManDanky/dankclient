"""Shorthand in 3kdb's map is written out as the command it stands for.

`l` is an alias on 3K's side, and a player's aliases are their own -- one
tester's `l` is his corpse command.  `efor` is a tt++ alias for `portal
eforest` that 3K has never heard of.  3kdb's map has both as ways out: four
`l` exits (three beside a `look` to the same room) and one `efor` beside
`portal eforest`.  A walk that took one sent it.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.tintin import import_map, translate_step  # noqa: E402

# The shapes as 3kdb's map has them, trimmed.
MAP = """C 99999

V 20231

R {148}{0}{<278>}{The entrance to Fantasy (w,e,portal)}{-+-}{A portal.}{Pinnacle}{}{}{}{1.000}{1}
E {4297}{portal eforest}{portal eforest}{0}{2}{}{1.000}{}{0.00}
E {4297}{efor}{efor}{0}{2}{}{1.000}{}{0.00}
R {4297}{0}{<118>}{Road in the Forest (e)}{|}{Trees.}{Forest}{}{}{}{1.000}{1}
R {38152}{0}{<108>}{Falling down a chasm!!}{[ ]}{You are falling.}{Chasm}{}{}{}{1.000}{1}
E {37410}{look}{look}{1}{0}{}{1.000}{}{0.00}
E {37410}{l}{l}{0}{0}{}{1.000}{}{0.00}
R {37410}{0}{<118>}{The bottom (u)}{|}{Ouch.}{Chasm}{}{}{}{1.000}{1}
R {45755}{0}{}{You drift under the old stone bridge...}{ }{}{Tunnels}{}{}{}{1.000}{1}
E {45756}{l}{l}{0}{0}{}{1.000}{}{0.00}
R {45756}{0}{}{Under (s)}{ }{Rocks.}{Tunnels}{}{}{}{1.000}{1}
"""


def commands(store: Store, room: int) -> set[str]:
    return {str(e["command"]) for e in store.exits_from(room)}


def test_the_importer_writes_shorthand_out():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "3k.map"
        path.write_text(MAP)
        store = Store()
        import_map(store, path)
        assert commands(store, 148) == {"portal eforest"}
        assert commands(store, 38152) == {"look"}
        assert commands(store, 45755) == {"look"}, "an `l` on its own is renamed"


def test_a_walk_through_them_types_the_whole_command():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "3k.map"
        path.write_text(MAP)
        store = Store()
        import_map(store, path)
        m = Mapper(store)
        assert m.route(4297, start=148) == ["portal eforest"]
        assert m.route(45756, start=45755) == ["look"]


def test_a_map_imported_before_is_put_right_once():
    """A merge only ever adds, so a map that already holds them keeps them
    unless something takes them out."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "map.sqlite"
        store = Store(path)
        gate, road = store.add_room("The entrance to Fantasy"), store.add_room("Road")
        chasm, bottom = store.add_room("Falling"), store.add_room("The bottom")
        bridge, under = store.add_room("Drifting"), store.add_room("Under")
        store.link(gate, "portal eforest", road)
        store.link(gate, "efor", road)
        store.link(chasm, "look", bottom)
        store.link(chasm, "l", bottom)
        store.link(bridge, "l", under)
        store.db.execute("DELETE FROM meta WHERE key = 'forgot:shorthand'")
        store.close()

        store = Store(path)
        assert commands(store, gate) == {"portal eforest"}
        assert commands(store, chasm) == {"look"}
        assert commands(store, bridge) == {"look"}
        # Once per map: a way out somebody adds afterwards is theirs.
        store.link(bridge, "l", road)
        store.close()
        store = Store(path)
        assert "l" in commands(store, bridge)
        store.close()


def test_a_bot_path_gets_the_same_treatment():
    assert translate_step("n;l;efor;w", {}) == ("n;look;portal eforest;w", "")


def test_a_command_that_only_starts_the_same_is_left_alone():
    assert translate_step("lick;effort;look", {}) == ("lick;effort;look", "")
