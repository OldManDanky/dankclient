"""Finding yourself again by name, without taking the step twice.

Lost, with the title saying "Eastwick" -- and 3K's Chaos has three rooms
called Eastwick with the same four exits.  The mapper narrowed them by the
command just walked, but walked it *from* the named rooms: those are where
you might have arrived, not where you started, so it took the step a second
time.  West of one of the Eastwicks is Eastwick Road, and that is where it
put a player who had walked west into Eastwick, and a room ahead of them from
then on.  What narrows the named rooms is where you might have been.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.mapper import Mapper  # noqa: E402
from mud.store import Store  # noqa: E402

FOUR = ["e", "n", "s", "w"]


def chaos():
    """Two Eastwicks alike in name and exits; west of one is Eastwick Road."""
    store = Store()
    t = 0.0
    start = store.add_room("A Crossing", t)
    near = store.add_room("Eastwick", t)       # the one west of the crossing
    far = store.add_room("Eastwick", t)        # the one with the road to its west
    road = store.add_room("Eastwick Road", t)
    for room, exits in ((start, ["w"]), (near, FOUR), (far, FOUR), (road, FOUR)):
        store.observe(room, exits, [], t)
    store.link(start, "w", near, t)
    store.link(far, "w", road, t)
    store.locked = True               # an imported map, as the real one is
    return store, start, near, road


def test_the_name_is_narrowed_by_where_you_came_from():
    store, start, near, road = chaos()
    m = Mapper(store)
    m.here, m.candidates = None, [start]          # lost, but somewhere near here
    m.sent("w", 100.0)
    here = m.arrived(FOUR, [], name="Eastwick", at=100.2)
    assert here == near, "not Eastwick Road, which is west of the other Eastwick"


def test_with_nothing_to_tell_them_apart_it_is_never_put_on_the_road():
    """No idea where we were, and two Eastwicks to choose from: honestly lost
    is right.  Eastwick Road -- a room the title says we are not in -- is not."""
    store, start, near, road = chaos()
    m = Mapper(store)
    m.here, m.candidates = None, []               # no idea where we were
    m.sent("w", 100.0)
    m.arrived(FOUR, [], name="Eastwick", at=100.2)
    assert m.here != road
    assert m.here is None
