"""A room whose ways out 3K does not list.

Pure light, at the top of the Tree of Life, is left by `w` and `will`, and
its DDD lists nothing at all.  The map followed `light` from the Temple of
Keter, saw exits that did not match, and lost itself there on every visit.
An empty list says nothing; the room's own title says where we are.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402


def tree():
    store = Store()
    m = Mapper(store)
    keter = store.add_room("Temple of Keter")
    light = store.add_room("Pure light")
    store.observe(keter, ["light", "turnaway"], [])
    store.observe(light, ["w", "will"], [])
    store.link(keter, "light", light)
    m.here = keter
    m.sent("light", at=0.0)
    return m, light


def test_no_ways_out_listed_and_the_title_names_where_the_edge_leads():
    m, light = tree()
    assert m.arrived([], [], name="Pure light", at=0.1) == light
    assert m.here == light


def test_but_not_when_the_title_names_somewhere_else():
    m, light = tree()
    m.arrived([], [], name="A dark pit", at=0.1)
    assert m.here != light


def test_and_exits_that_disagree_still_disagree():
    m, light = tree()
    m.arrived(["n", "s"], [], name="Pure light", at=0.1)
    assert m.here != light
