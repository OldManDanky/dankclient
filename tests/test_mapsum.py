"""Comparing your map with somebody else's, without sending the map.

A map is tens of megabytes and its file holds that player's session log, so
what travels is a summary: counts, digests and area names.  Same digest,
same map; and when they differ, the summary has to say how.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, mapsum  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402


def a_map(extra: bool = False) -> Store:
    """Three rooms in a line, and a fourth if `extra`."""
    s = Store()
    cot = s.add_room("The Center of Town")
    square = s.add_room("A Dark Square")
    hall = s.add_room("A Great Hall")
    s.observe(cot, ["n", "e"], ["sky"])
    s.link(cot, "n", square)
    s.link(square, "s", cot)
    s.link(square, "e", hall)
    if extra:
        attic = s.add_room("An Attic")
        s.link(hall, "u", attic)
    return s


def areas(store: Store, rooms: dict[int, str]) -> None:
    """Put rooms in areas, as the importer does."""
    for n, (room_id, name) in enumerate(rooms.items(), start=1):
        store.db.execute("INSERT OR IGNORE INTO region (id, name) VALUES (?,?)", (n, name))
        store.db.execute("UPDATE room SET region_id = ? WHERE id = ?", (n, room_id))


def test_the_same_map_has_the_same_digest():
    mine, theirs = mapsum.summarize(a_map()), mapsum.summarize(a_map())
    assert mine["digest"] == theirs["digest"]
    assert mapsum.compare(mine, theirs) == ["the same map, exactly: " + mine["digest"]]
    assert mine["counts"] == {"rooms": 3, "exits": 3, "walked": 3, "named": 0,
                              "areas": 0, "fingerprints": 1}


def test_a_room_or_exit_they_do_not_have():
    said = "\n".join(mapsum.compare(mapsum.summarize(a_map(extra=True)),
                                    mapsum.summarize(a_map())))
    assert said.startswith("not the same map.")
    assert "rooms: 4 yours, 3 theirs (+1)" in said
    assert "exits: 4 yours, 3 theirs (+1)" in said


def test_the_same_3kdb_file_built_by_a_different_importer():
    mine, theirs = a_map(), a_map(extra=True)
    mine.set_setting("3kdb:map", "abc123/2")
    theirs.set_setting("3kdb:map", "abc123/1")
    said = "\n".join(mapsum.compare(mapsum.summarize(mine), mapsum.summarize(theirs)))
    assert "the same file, built by a different importer (2 yours, 1 theirs)" in said
    assert "Take updates" in said


def test_one_of_you_never_took_it():
    mine, theirs = a_map(), a_map(extra=True)
    mine.set_setting("3kdb:map", "abc123/2")
    said = "\n".join(mapsum.compare(mapsum.summarize(mine), mapsum.summarize(theirs)))
    assert "they have no record of taking it (yours: abc123/2)" in said


def test_it_says_which_areas_differ():
    mine, theirs = a_map(extra=True), a_map()
    for store in (mine, theirs):
        areas(store, {1: "Town", 3: "Hell"})
    got = mapsum.compare(mapsum.summarize(mine), mapsum.summarize(theirs))
    assert any("area(s) differ" in line for line in got), got
    assert any("Hell" in line for line in got), "the area with the extra exit"


def test_the_summary_carries_nothing_of_yours():
    store = a_map()
    store.rename(2, "My Own Name For This")
    store.db.execute("INSERT INTO landmark (name, room_id) VALUES ('cot', 1)")
    areas(store, {1: "Town"})
    text = json.dumps(mapsum.summarize(store))
    for private in ("Center of Town", "Dark Square", "My Own Name For This", "cot"):
        assert private not in text, private
    assert "Town" in text, "area names are 3kdb's, and are what a difference is reported by"


def test_lines_say_what_it_was_built_from():
    store = a_map()
    store.set_setting("3kdb:map", "abc1234567890/2")
    store.locked = True
    said = "\n".join(mapsum.lines(mapsum.summarize(store)))
    assert "3 rooms, 3 exits" in said and "locked" in said
    assert "abc1234567" in said and "importer 2" in said


def test_the_commands():
    where = Path(tempfile.mkdtemp())
    session = Session("127.0.0.1", 1, sec_code=1, store=a_map())
    said: list[str] = []
    assert commands.handle(f"/mapsum {where}/mine.json", session, None, said.append)
    assert "map digest" in said[-1] and str(where) in said[-1]
    assert (where / "mine.json").exists()
    said.clear()
    commands.handle(f"/mapcheck {where}/mine.json", session, None, said.append)
    assert said[-1].startswith("the same map, exactly")
    said.clear()
    commands.handle("/mapcheck", session, None, said.append)
    assert said[-1].startswith("usage: /mapcheck")
    said.clear()
    commands.handle(f"/mapcheck {where}/nope.json", session, None, said.append)
    assert "could not read" in said[-1]


def test_a_summary_from_a_newer_client():
    mine = mapsum.summarize(a_map())
    said = mapsum.compare(mine, {"summary": 99, "digest": "x"})
    assert "version 99" in said[0] and str(mapsum.VERSION) in said[0]
