"""Read a TinTin++ map, and the speedrun list that goes with it.

Players have walked 3K for years with tt++ and have the maps to show for it.
The one this was written against holds 49,494 named rooms and 154,073 exits,
with the area each room belongs to and the short note it is speedwalked by.
Rebuilding that by walking would take months.

The two formats, as they actually appear in ``3k_shared.map`` (V 20231)::

    R {vnum}{flags}{colour}{name (exits)}{symbol}{description}{area}{note}...
    E {to}{direction}{command}{...}

An ``E`` belongs to the ``R`` above it.  Fields are brace-delimited and nest --
the room data field holds ``{{mobs} {Cancer}}`` -- so they are read by depth
rather than by splitting.

Room numbers are kept as room ids.  The speedrun list refers to rooms by vnum
and so does everything a player has written over the years, and an import that
renumbered them would throw that away for nothing.

What is deliberately *not* imported is any claim about what a room looks like.
tt++ identifies rooms by matching descriptions; this client identifies them by
where you walked, and the imported exits are enough for that.  Fingerprints
are learned by visiting, so the map gets more certain as it is used rather
than starting out sure and being wrong.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from .codes import parse_bad
from .store import personal

#: .add_speedrun {name} {type} {vnum} {description}
SPEEDRUN = re.compile(
    r"^\s*\.?add_speedrun\s*\{(.*?)\}\s*\{(.*?)\}\s*\{(\d+)\}\s*\{(.*?)\}\s*;?\s*$"
)


def fields(rest: str) -> list[str]:
    """Split ``{a}{b}{{c} {d}}`` into its top-level fields."""
    out: list[str] = []
    depth, start = 0, None
    for i, ch in enumerate(rest):
        if ch == "{":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(rest[start:i])
                start = None
            elif depth < 0:                   # stray brace; give up on the line
                return out
    return out


def read_map(path: str | Path) -> Iterator[tuple[str, list[str]]]:
    """Yield ("R" | "E", fields) in file order, ignoring everything else."""
    with open(path, encoding="latin-1") as handle:
        for line in handle:
            if len(line) < 3 or line[1] != " " or line[0] not in "RE":
                continue
            got = fields(line[2:])
            if got:
                yield line[0], got


#: tt++ directives that are the client talking to itself.  `#map goto
#: $puddle_room` moves tt++'s own cursor; 3K has never heard of it.
CLIENT_ONLY = {"map", "class", "read", "var", "if", "else", "elseif", "line",
               "nop", "highlight", "showme", "echo", "unvar", "script",
               "format", "math", "list", "return", "end"}

REPEAT = re.compile(r"^#(\d+)\s+(.+)$")
DELAY = re.compile(r"^#delay\s+[\d.]+\s+(.+)$", re.I)
SEND = re.compile(r"^#send\s+(.+)$", re.I)
DIRECTIVE = re.compile(r"^#(\w+)")

#: No edge is worth more than this many commands.  `#31 climb` is real and
#: means it, but a mis-read number should not empty the rate limiter.
MOST_REPEATS = 50


def walkable(command: str) -> str:
    """A tt++ exit reduced to what can actually be typed at 3K.

    3kdb records client directives inside exits and they are not all the same
    kind of thing.  Measured over the 472 in a 49,494-room map: 439 are `#map`,
    which moves tt++'s own cursor and means nothing here; 24 are `#4 turn left
    dial`, where the number is a repeat count and the rest is a real command
    worth keeping; the last nine are #delay, #send, #if and #read.

    So this is not "drop anything with a hash in it", which would throw away
    the command inside every repeat -- and it is not "send it and find out",
    which types `#map goto $puddle_room` into the game and spends a command
    against the rate the MUD is watching.
    """
    # Only touch a command that has something in it for tt++.  This is a
    # filter, not a formatter: rebuilding the string also normalises the
    # spacing, and "search;open trapdoor; stairs" rebuilt without its space is
    # a different string, so a map already holding the spaced one ends up with
    # both.  That happened -- 136 of them -- and they are the same way out.
    if not any(part.strip().startswith("#") for part in command.split(";")):
        return command

    out: list[str] = []
    for raw in command.split(";"):
        part = raw.strip()
        if not part:
            continue
        if not part.startswith("#"):
            out.append(part)
            continue

        hit = REPEAT.match(part)
        if hit:
            # "#10 {smash brick}" -- the braces group it, they are not typed.
            inner = hit.group(2).strip()
            if inner.startswith("{") and inner.endswith("}"):
                inner = inner[1:-1].strip()
            inner = walkable(inner)
            if inner:
                out += [inner] * min(int(hit.group(1)), MOST_REPEATS)
            continue

        hit = DELAY.match(part)
        if hit:
            # The waiting is this client's job, not something 3K is told.
            inner = walkable(hit.group(1).strip())
            if inner:
                out.append(inner)
            continue

        hit = SEND.match(part)
        if hit:
            out.append(hit.group(1).strip())
            continue

        word = DIRECTIVE.match(part)
        if word and word.group(1).lower() in CLIENT_ONLY:
            continue
        # An unknown directive is still a directive: it starts with a hash,
        # which no 3K command does.
    return ";".join(out)


def import_map(store, path: str | Path, progress=None,
               merge: bool = False) -> dict:
    """Load a tt++ map into the store.  Returns what it did.

    A first import owns the database and replaces what it finds.  A merge is
    for a map that has already been played on -- 3kdb gains areas, and pulling
    them in must not cost you the map you have.  So a merge only ever adds:
    rooms the map does not have, exits it does not have, and areas by the name
    they already go by.

    That restraint is the whole feature.  Replacing was measured against a map
    somebody had played on for one session: every region duplicated, every
    visit count reset to zero, every fingerprint the client had learned by
    walking wiped, every walked edge marked unwalked, and a room the player had
    renamed by hand put back to the name tt++ gave it.  An update button that
    does that is worse than no update button.

    Names are left alone on a merge, and that is deliberate: nothing here can
    tell a name the player corrected from a name that came out of the file, so
    the safe half is the one that keeps working.  `/name` is how a name
    changes.
    """
    db = store.db
    now = __import__("time").time()
    # OR IGNORE keeps what is already there; OR REPLACE is a fresh import
    # taking ownership of the file.
    verb = "INSERT OR IGNORE" if merge else "INSERT OR REPLACE"

    rooms: list[tuple] = []
    edges: list[tuple] = []
    prints: list[tuple] = []
    areas: dict[str, int] = {}
    current: int | None = None
    skipped = 0

    def flush() -> None:
        db.executemany(
            f"{verb} INTO room "
            "(id, name, region_id, first_seen, last_seen, visits, note) "
            "VALUES (?,?,?,?,?,0,?)", rooms)
        db.executemany(
            f"{verb} INTO fingerprint "
            "(room_id, exits, scenery, seen, last_seen) VALUES (?,?,'',0,?)",
            prints)
        rooms.clear()
        prints.clear()

    db.execute("BEGIN")
    try:
        for kind, got in read_map(path):
            if kind == "R":
                current = None
                if len(got) < 4 or not got[0].isdigit():
                    continue
                vnum = int(got[0])
                name, exits = parse_bad(got[3].strip())
                if not name:
                    skipped += 1              # an unused room number
                    continue
                area = got[6].strip() if len(got) > 6 else ""
                note = got[7].strip() if len(got) > 7 else ""
                if area and area not in areas:
                    # By name, not by insertion: a merge that made its own
                    # region rows gave a map two of every area, and the rooms
                    # split between them.
                    have = store.region_by_name(area) if merge else None
                    if have is not None:
                        areas[area] = int(have["id"])
                    else:
                        cur = db.execute(
                            "INSERT INTO region (name, parent_id, layout) "
                            "VALUES (?,NULL,'grid')", (area,))
                        areas[area] = int(cur.lastrowid)
                rooms.append((vnum, name, areas.get(area), now, now,
                              note or None))
                # The exits tt++ recorded in the room title are the same list
                # DDD sends, so dead reckoning can check itself against an
                # imported room from the first step.
                prints.append((vnum, ",".join(sorted(set(e.lower()
                                                        for e in exits))), now))
                current = vnum
                if len(rooms) >= 5000:
                    flush()
                    if progress:
                        progress(current)
            elif kind == "E" and current is not None:
                if len(got) < 3 or not got[0].isdigit():
                    continue
                command = walkable((got[2] or got[1]).strip().lower())
                # Somebody's own house, or somebody's own alias, is not a way
                # out of a public room.
                if command and not personal(command):
                    edges.append((current, command, int(got[0]), now))
        flush()

        # Edges last: every room exists by now, so a link to a room that was
        # never defined can be dropped rather than left dangling.
        known = {int(r["id"]) for r in db.execute("SELECT id FROM room")}
        good = [e for e in edges if e[2] in known and e[0] in known]
        db.executemany(
            f"{verb} INTO edge "
            "(from_room, command, to_room, seen, last_seen) VALUES (?,?,?,0,?)",
            good)
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    # tt++ leaves the exits out of some room titles -- 5.2% of one real map
    # -- but the ways out were mapped all the same, so take them from there.
    filled = store.backfill_exits()
    store.clean_exits()
    # Exits that came in before the importer knew to strip tt++ out of them.
    scrubbed = store.clean_edge_commands(walkable)
    # ...and exits that are the same way out spelled two ways.
    folded = store.fold_spaced_exits()
    # A merge into a map from before the importer knew better.
    store.forget_personal()

    # An imported map is finished: it should be corrected, not grown.
    store.locked = True

    return {"rooms": len(known), "edges": len(good),
            "dangling": len(edges) - len(good), "areas": len(areas),
            "blank": skipped, "backfilled": filled, "scrubbed": scrubbed,
            "folded": folded}



# --- 3kdb's bot library ------------------------------------------------------
#
# Two files describe each route::
#
#     common/bot/bots.tin      .add_bot {file} {alias} {desc} {vnum} {loop}
#                                       {playercheck} {tags}
#     common/bot/bots/<file>   #var bot[path] {n;w;{pick fruit;get seed;d};s}
#                              #list botmobs add {{{long} {A Root Warrior}
#                                                  {target} {warrior}}}
#
# The braces matter: a braced group is one step of several commands, and 164
# of the 172 routes use them.  So does the start room -- a path is written
# from one place, and walked from anywhere else it is fifty steps through the
# wrong part of the world.

ADD_BOT = re.compile(r"^\s*\.?add_bot\b(.*)$")
BRACED = re.compile(r"\{([^{}]*)\}")

#: What the fields mean, in order.  Everything after the fourth is optional.
BOT_FIELDS = ("file", "alias", "desc", "vnum", "loop", "polite", "tags")


def read_add_bot(line: str) -> dict | None:
    """The fields of one `.add_bot` line, or None if it is not one.

    3kdb writes six of them or seven: the tags on the end are optional, and 78
    of the 145 definitions leave them off.  Insisting on seven found 67 and
    silently skipped the rest -- Section Z, the Abyss, the Catacombs, the
    Portal of Life -- with nothing to say it had, because a line that does not
    match is not a line that failed.
    """
    head = ADD_BOT.match(line)
    if head is None:
        return None
    got = [field.strip() for field in BRACED.findall(head.group(1))]
    if len(got) < 4:                       # file, alias, desc and a room
        return None
    got += [""] * (len(BOT_FIELDS) - len(got))
    return dict(zip(BOT_FIELDS, got))
BOT_PATH = re.compile(r"#var\s*\{?bot\[path\]\}?\s*\{")
BOT_MOB = re.compile(r"\{long\}\s*\{(.*?)\}\s*\{target\}\s*\{(.*?)\}")
BOT_SETUP = re.compile(r"^\s*(?!#|\.)([a-z][\w ]*)\s*;\s*$")


def read_bot(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="latin-1", errors="replace")
    # Read to the matching brace rather than to a line end: the path itself
    # contains braces, and anchoring on the line would either stop at the
    # first group or run to the end of the file.
    hit = BOT_PATH.search(text)
    walk = ""
    if hit:
        depth, out = 1, []
        for ch in text[hit.end():]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(ch)
        walk = "".join(out).strip()
    mobs = BOT_MOB.findall(text)
    setup = [m.group(1).strip() for line in text.splitlines()
             if (m := BOT_SETUP.match(line)) and m.group(1).strip() != "close"]
    return {
        "path": walk,
        # The short name is what you type; the long one is how MIP describes
        # it.  Either matches, so keeping both costs nothing and the long one
        # is what makes "archangel" stand for all ten of them.
        "targets": sorted({t.strip() for _, t in mobs}
                          | {long.strip() for long, _ in mobs}),
        "setup": "\n".join(setup),
    }


def import_bots(routes, root: str | Path, note=None) -> dict:
    """Read 3kdb's bot library into a RouteStore.  Returns what it did.

    A route you have edited is never overwritten.  These are somebody else's
    paths and yours are yours: an update that silently replaced the version
    you fixed would be the same mistake as a map import that resets what you
    have walked.
    """
    root = Path(root)
    listing = root / "common" / "bot" / "bots.tin"
    if not listing.exists():
        return {"added": 0, "kept": 0, "skipped": 0, "missing": str(listing)}

    known = {r.name for r in routes.routes}
    added = kept = skipped = 0
    for line in listing.read_text(encoding="latin-1").splitlines():
        got = read_add_bot(line)
        if got is None:
            continue
        file, alias, desc = got["file"], got["alias"], got["desc"]
        vnum, loop, polite = got["vnum"], got["loop"], got["polite"]
        body = root / "common" / "bot" / "bots" / f"{file}.tin"
        if not body.exists():
            skipped += 1
            continue
        data = read_bot(body)
        if not data["path"]:
            skipped += 1
            continue
        name = alias or file
        if name in known:
            kept += 1                      # yours, and it stays yours
            continue
        route, problem = routes.upsert({
            "name": name,
            "path": data["path"],
            "targets": data["targets"],
            "setup": data["setup"],
            "start": int(vnum) if vnum.isdigit() else 0,
            "loop": loop not in ("", "0"),
            "polite": polite not in ("", "0"),
        })
        if problem:
            skipped += 1
            continue
        added += 1
        if note:
            note(f"  {name:<22} {len(route.steps()):>4} steps  "
                 f"{len(route.targets):>2} targets  start #{route.start}"
                 f"  {desc[:36]}")
    return {"added": added, "kept": kept, "skipped": skipped, "missing": ""}


def import_speedruns(store, path: str | Path) -> tuple[int, list[str]]:
    """Load ``.add_speedrun {name} {type} {vnum} {description}`` entries.

    Returns how many landed and the names of the ones that point at rooms this
    map does not have.
    """
    db = store.db
    known = {int(r["id"]) for r in db.execute("SELECT id FROM room")}
    added, missing = 0, []
    db.execute("BEGIN")
    try:
        for line in Path(path).read_text(encoding="latin-1").splitlines():
            hit = SPEEDRUN.match(line)
            if hit is None:
                continue
            name, kind, vnum, desc = hit.groups()
            if int(vnum) not in known:
                # A speedrun outliving the room it pointed at.  Years of
                # edits will do that, and it is not a reason to refuse the
                # other four hundred.
                missing.append(name.strip())
                continue
            db.execute(
                "INSERT OR REPLACE INTO landmark (name, room_id, kind, note) "
                "VALUES (?,?,?,?)", (name.strip(), int(vnum), kind.strip(),
                                     desc.strip()))
            added += 1
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return added, missing


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .store import Store

    p = argparse.ArgumentParser(prog="mud.tintin",
                                description="import a TinTin++ map")
    p.add_argument("map", help="a .map file written by tt++")
    p.add_argument("--into", default="map.sqlite", metavar="FILE")
    p.add_argument("--speedruns", metavar="FILE",
                   help="a .tin file of .add_speedrun entries")
    args = p.parse_args(argv)

    store = Store(args.into)
    result = import_map(store, args.map,
                        progress=lambda v: print(f"  ...room {v}", flush=True))
    print(f"{result['rooms']} rooms, {result['edges']} exits, "
          f"{result['areas']} areas"
          + (f", {result['backfilled']} took their exits from their edges"
             if result["backfilled"] else "")
          + (f", {result['dangling']} exits led nowhere" if result["dangling"]
             else "")
          + (f", {result['blank']} unused room numbers" if result["blank"]
             else ""))
    if args.speedruns:
        added, missing = import_speedruns(store, args.speedruns)
        print(f"{added} landmarks"
              + (f", {len(missing)} point at rooms the map does not have: "
                 + ", ".join(missing[:8]) if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
