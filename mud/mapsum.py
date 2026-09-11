"""A map's summary, for comparing one player's map with another's.

Two people cannot hand each other a map: it is tens of megabytes, and the
file also holds that player's session log.  What they can exchange is this
-- counts, digests and area names, nothing else.  Same digest, same map.

`/mapsum` prints it and writes the file; `/mapcheck <file>` compares the one
somebody sent with your own and says where the two differ.  Most differences
turn out to be the import: which 3kdb map file was taken, and which version
of the importer built it, both of which the map records.
"""

from __future__ import annotations

import hashlib
import json
import time

VERSION = 1


def _digest(rows) -> str:
    h = hashlib.sha256()
    for row in rows:
        h.update(("\x1f".join("" if v is None else str(v) for v in row) + "\x1e").encode())
    return h.hexdigest()[:16]


def summarize(store) -> dict:
    """Everything the comparison needs, and nothing of anybody's own."""
    db = store.db
    marks = {k: v for k, v in db.execute(
        "SELECT key, value FROM meta WHERE key LIKE '3kdb:%'")}
    one = lambda sql: db.execute(sql).fetchone()[0]          # noqa: E731
    counts = {
        "rooms": one("SELECT count(*) FROM room"),
        "exits": one("SELECT count(*) FROM edge WHERE failed = 0"),
        "walked": one("SELECT count(*) FROM edge WHERE seen > 0"),
        "named": one("SELECT count(*) FROM landmark"),
        "areas": one("SELECT count(*) FROM region"),
        "fingerprints": one("SELECT count(*) FROM fingerprint"),
    }
    # One pass over the rooms and one over the exits: an area at a time would
    # be 777 passes over a hundred and forty thousand exits.
    area_of: dict[int, str] = {}
    areas: dict[str, dict] = {}
    for name, room_id in db.execute(
            "SELECT coalesce(r.name, '(no area)'), m.id FROM room m "
            "LEFT JOIN region r ON r.id = m.region_id ORDER BY 1, 2"):
        area_of[room_id] = name
        got = areas.setdefault(name, {"rooms": 0, "exits": 0, "rows": []})
        got["rooms"] += 1
    for row in db.execute("SELECT from_room, command, to_room FROM edge "
                          "WHERE failed = 0 ORDER BY from_room, command"):
        name = area_of.get(row[0])
        if name is not None:
            areas[name]["rows"].append(tuple(row))
    for got in areas.values():
        rows = got.pop("rows")
        got["exits"] = len(rows)
        got["digest"] = _digest(rows)
    return {
        "summary": VERSION,
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "locked": store.setting("locked", "") == "1",
        "marks": marks,
        "counts": counts,
        "digest": _digest(db.execute("SELECT id, name FROM room ORDER BY id"))
                  + "-" + _digest(db.execute(
                      "SELECT from_room, command, to_room FROM edge "
                      "WHERE failed = 0 ORDER BY from_room, command")),
        "areas": areas,
    }


def lines(got: dict) -> list[str]:
    """A summary as the output shows it."""
    c = got["counts"]
    out = [f"map digest {got['digest']}",
           f"  {c['rooms']} rooms, {c['exits']} exits, {c['areas']} areas; "
           f"{c['walked']} exits walked, {c['named']} of your own names"
           + (", locked" if got.get("locked") else "")]
    for key, mark in sorted(got.get("marks", {}).items()):
        sha, _, version = mark.partition("/")
        out.append(f"  from 3kdb: {key[5:]:<10} {sha[:10]}"
                   + (f"  (importer {version})" if version else "  (before the "
                      "importer said which version it was)"))
    return out


def compare(mine: dict, theirs: dict, most: int = 12) -> list[str]:
    """Where two maps differ, the coarsest thing first."""
    if theirs.get("summary") != VERSION:
        return [f"that file says it is a summary of version "
                f"{theirs.get('summary')!r}; this client writes {VERSION}"]
    out: list[str] = []
    if mine["digest"] == theirs["digest"]:
        return ["the same map, exactly: " + mine["digest"]]
    out.append("not the same map.")
    for key in sorted(set(mine["marks"]) | set(theirs["marks"])):
        a, b = mine["marks"].get(key, ""), theirs["marks"].get(key, "")
        if a != b:
            same_file = a.partition("/")[0] == b.partition("/")[0]
            out.append(f"  3kdb {key[5:]}: "
                       + ("the same file, built by a different importer "
                          f"({a.partition('/')[2] or '?'} yours, "
                          f"{b.partition('/')[2] or '?'} theirs) -- "
                          "Options -> Updates -> Take updates rebuilds it"
                          if same_file else
                          "neither has a record of taking it" if not a and not b else
                          f"they have no record of taking it (yours: {a[:10]})"
                          if not b else
                          f"you have no record of taking it (theirs: {b[:10]})"
                          if not a else
                          f"a different file ({a[:10]} yours, {b[:10]} theirs)"))
    for what in ("rooms", "exits", "areas"):
        a, b = mine["counts"][what], theirs["counts"][what]
        if a != b:
            out.append(f"  {what}: {a} yours, {b} theirs ({a - b:+d})")
    differ = []
    for name in sorted(set(mine["areas"]) | set(theirs["areas"])):
        a = mine["areas"].get(name, {"rooms": 0, "exits": 0, "digest": ""})
        b = theirs["areas"].get(name, {"rooms": 0, "exits": 0, "digest": ""})
        if a["digest"] != b["digest"]:
            differ.append((abs(a["rooms"] - b["rooms"]) + abs(a["exits"] - b["exits"]),
                           name, a, b))
    if not differ:
        return out + ["  every area matches; the difference is in the room names"]
    differ.sort(key=lambda row: -row[0])
    out.append(f"  {len(differ)} area(s) differ, the widest first:")
    for _size, name, a, b in differ[:most]:
        out.append(f"    {name:<28} rooms {a['rooms']:>5} / {b['rooms']:<5}"
                   f"  exits {a['exits']:>5} / {b['exits']:<5}"
                   + ("  (theirs only)" if not a["rooms"] else
                      "  (yours only)" if not b["rooms"] else ""))
    if len(differ) > most:
        out.append(f"    ... and {len(differ) - most} more")
    return out


def write(path, got: dict) -> None:
    from .paths import write_atomically
    write_atomically(path, json.dumps(got, indent=1, sort_keys=True))


def read(path) -> dict:
    from pathlib import Path
    return json.loads(Path(path).read_text())
