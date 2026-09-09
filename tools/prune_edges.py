#!/usr/bin/env python3
"""Take out exits the client invented while it was blaming the wrong command.

A route sends its housekeeping and its next step in one breath -- "wrap all",
"disperse corpse", "divvy gold", "w" -- and the mapper used to credit the
oldest of them with the room block that only the last one caused.  That lost
its place, and it wrote the mistake into the map: six "wrap all" edges and a
"disperse corpse" across the chess board, which the panel then drew squares
along, so an eight-by-eight board came out ten wide with rooms in the wrong
squares.

Both halves are fixed -- the queue prefers a command the room has a way out
for, and a locked map no longer grows an edge it was only guessing at -- but
the edges already written stay written.  This is for those.

What it will not touch:

  * anything that came with the map.  tt++ stores speedwalks as edges on
    purpose -- ".gohome", "mines 1", "push button;e" -- and they are not
    mistakes.  Only edges somebody has actually walked are considered.
  * anything the room lists as an exit, whether that is "n" or "enter" or
    "climb pipe".  DDD names every way out, and the map's own edges name the
    rest.
  * a plain direction.  A room's recorded exits can be short -- tt++ truncates
    a long room title at sixty characters, brackets and all -- so "e" missing
    from the list is more likely a gap in the record than an invented exit.
    Unless it leads back to the room it started in, which no direction does.

What is left still needs somebody who knows the MUD.  "board cot" at the
Academy landing pad is a shuttle; "embrace void" is an emote everywhere in 3K
except one room in Eastwick, where it takes you to the Angels 2.0 area;
"climb down" is how you get off the chess board; a shop has "home", "chaos",
"smithy" and the rest, which teleport you out.  All of those belong in the
map, and from here they look exactly like the mistakes.  So this prints and
stops, and takes nothing out without --yes; --command and --from narrow it to
the ones you have decided about.

--disputed asks a different question: where does the client disagree with the
imported map about an ordinary direction?  Only one of the two can be right,
and the map is the one that was not written by a client blaming the wrong
command for a room block.  Three edges pointing "s", "w" and "e" at the
chessboard entrance from rooms nowhere near it made /go chess route through a
wall.  A door and a lift really do have two destinations, though, so this is a
question too.

    python3 tools/prune_edges.py map.sqlite
    python3 tools/prune_edges.py map.sqlite --command "wrap all" \
                                            --command "disperse corpse" --yes
    python3 tools/prune_edges.py map.sqlite --disputed
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.store import Store  # noqa: E402


def ways_out(store: Store, room: int) -> set[str]:
    """Every command this room has ever been seen to have a way out for."""
    ways = set()
    for row in store.db.execute(
            "SELECT exits FROM fingerprint WHERE room_id = ?", (room,)):
        ways |= {e.strip().lower()
                 for e in (row["exits"] or "").split(",") if e.strip()}
    # An edge nobody has walked came with the map, and the map is the
    # authority on what that room's odd ways out are.
    ways |= {str(r["command"]).strip().lower() for r in store.db.execute(
        "SELECT command FROM edge WHERE from_room = ? AND seen = 0", (room,))}
    return ways


#: Directions.  Always real movement, so a missing one is a gap in the record.
COMPASS = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "u", "d",
           "north", "south", "east", "west", "up", "down", "in", "out",
           "northeast", "northwest", "southeast", "southwest"}


def suspect(store: Store, only: set[str] | None = None) -> list:
    out = []
    for edge in store.db.execute(
            "SELECT * FROM edge WHERE seen > 0 ORDER BY from_room, command"):
        cmd = str(edge["command"]).strip().lower()
        if only is not None and cmd not in only:
            continue
        loop = edge["from_room"] == edge["to_room"]
        if cmd in COMPASS and not loop:
            continue
        if not loop and cmd in ways_out(store, edge["from_room"]):
            continue
        out.append(edge)
    return out


def disputed(store: Store, only: set[str] | None = None) -> list:
    """Edges we walked that contradict the map on where a command goes.

    The importer walked 3K with tt++ and wrote down where "s" goes from the
    centre of Chaos.  If we later recorded the same command from the same room
    arriving somewhere else, one of the two is wrong, and the map is the one
    that was not being written by a client blaming the wrong command for a
    room block.

    Not always wrong, though: a door, a lift, a random exit genuinely does
    have more than one destination, and the schema allows that on purpose.
    So this is a question, not a verdict.
    """
    out = []
    for edge in store.db.execute("""
            SELECT ours.* FROM edge ours JOIN edge theirs
              ON theirs.from_room = ours.from_room
             AND theirs.command = ours.command
             AND theirs.to_room != ours.to_room
            WHERE ours.seen > 0 AND theirs.seen = 0
            ORDER BY ours.from_room, ours.command"""):
        if only is not None and str(edge["command"]).strip().lower() not in only:
            continue
        out.append(edge)
    return out


def show(store: Store, edges: list) -> None:
    for edge in edges:
        a = store.room(edge["from_room"])
        b = store.room(edge["to_room"])
        print(f"  {edge['from_room']:>6} {str(edge['command'])[:20]:<20} -> "
              f"{edge['to_room']:<6}  walked {edge['seen']}x   "
              f"{(a['name'] if a else '?')[:24]} -> {(b['name'] if b else '?')[:24]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("map", nargs="?", default="map.sqlite")
    ap.add_argument("--yes", action="store_true", help="actually remove them")
    ap.add_argument("--command", action="append", metavar="CMD",
                    help="only this command; repeatable")
    ap.add_argument("--disputed", action="store_true",
                    help="instead, edges that contradict the imported map "
                         "about where a command goes")
    ap.add_argument("--from", dest="rooms", action="append", type=int,
                    metavar="ROOM", help="only edges out of this room; "
                                         "repeatable")
    args = ap.parse_args(argv[1:])

    store = Store(args.map)
    only = ({c.strip().lower() for c in args.command}
            if args.command else None)
    found = (disputed(store, only) if args.disputed else suspect(store, only))
    # Narrow before printing.  A tool whose whole point is "read this before
    # you do it" must not print a list it is not about to act on.
    if args.rooms:
        found = [e for e in found if e["from_room"] in set(args.rooms)]
    if not found:
        print("nothing to take out")
        return 0

    show(store, found)

    if not args.yes:
        what = ("edges that contradict the map about where a command goes"
                if args.disputed else "exits the rooms have no way out for")
        print(f"\n{len(found)} {what}.  Read them before you take them out:\n"
              f"  some are real -- a door has two destinations, and 3K has ways "
              f"to travel\n  that are not directions -- and they look the same "
              f"from here.\n"
              f"  --command and --from narrow it, --yes does it.")
        return 0

    for edge in found:
        store.db.execute(
            "DELETE FROM edge WHERE from_room = ? AND command = ? AND to_room = ?",
            (edge["from_room"], edge["command"], edge["to_room"]))
    store.db.commit()
    print(f"\nremoved {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
