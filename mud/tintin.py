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

#: tt++'s room flag for a *void* room: a spacer for drawing a long way
#: between two rooms, not a room in the game.  Walking into one carries on to
#: the room beyond it, so an exit into one leads, in 3K, to wherever the
#: spacers end.
VOID = 8

#: Rows per transaction when importing.  Take updates runs beside a live
#: session, and one transaction for the whole merge held the file for as long
#: as the merge took -- four seconds here, longer on a slower machine with a
#: virus scanner watching -- so the session's own writes, which wait five,
#: failed with "database is locked".  In pieces, the session's writes go in
#: between.  A merge only adds, so stopping halfway leaves nothing wrong, and
#: it is recorded as taken only once all of it is in.
CHUNK = 5000

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
    #: spacer rooms, and where each one's exits go
    voids: dict[int, list[int]] = {}
    #: rooms tt++ never caught a name for: vnum -> (region, note)
    unnamed: dict[int, tuple] = {}
    in_void = False

    def flush() -> None:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.executemany(
                f"{verb} INTO room "
                "(id, name, region_id, first_seen, last_seen, visits, note) "
                "VALUES (?,?,?,?,?,0,?)", rooms)
            db.executemany(
                f"{verb} INTO fingerprint "
                "(room_id, exits, scenery, seen, last_seen) VALUES (?,?,'',0,?)",
                prints)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        rooms.clear()
        prints.clear()

    try:
        for kind, got in read_map(path):
            if kind == "R":
                current, in_void = None, False
                if len(got) < 4 or not got[0].isdigit():
                    continue
                vnum = int(got[0])
                flags = int(got[1]) if got[1].strip().isdigit() else 0
                name, exits = parse_bad(got[3].strip())
                area = got[6].strip() if len(got) > 6 else ""
                note = got[7].strip() if len(got) > 7 else ""
                if not name and flags & VOID:
                    # A spacer.  Its exits say where the corridor goes on to;
                    # the room itself is not one anybody stands in.
                    voids[vnum] = []
                    current, in_void = vnum, True
                    continue
                if not name:
                    # Either an unused number or a real room tt++ never caught
                    # a title for -- 2,225 of them in 3kdb's map, on the only
                    # way into the Underdark, Westersea and Xenolocles.  Its
                    # exits, read next, say which.
                    unnamed[vnum] = (area, note)
                    current = vnum
                    continue
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
                if len(rooms) >= CHUNK:
                    flush()
                    if progress:
                        progress(current)
            elif kind == "E" and current is not None:
                if len(got) < 3 or not got[0].isdigit():
                    continue
                if in_void:
                    voids[current].append(int(got[0]))
                    continue
                command = walkable((got[2] or got[1]).strip().lower())
                # Somebody's own house, or somebody's own alias, is not a way
                # out of a public room.
                if command and not personal(command):
                    edges.append((current, command, int(got[0]), now))

        # A room with no name is a room if it has a way out; otherwise it is a
        # number nobody used.  Its exits come from its edges below, the way a
        # bare title's do.
        leads = {e[0] for e in edges}
        for vnum, (area, note) in unnamed.items():
            if vnum not in leads:
                skipped += 1              # an unused room number
                continue
            if area and area not in areas:
                have = store.region_by_name(area) if merge else None
                if have is not None:
                    areas[area] = int(have["id"])
                else:
                    cur = db.execute(
                        "INSERT INTO region (name, parent_id, layout) "
                        "VALUES (?,NULL,'grid')", (area,))
                    areas[area] = int(cur.lastrowid)
            rooms.append((vnum, None, areas.get(area), now, now, note or None))
            prints.append((vnum, "", now))
        flush()

        # Through the spacers: an exit into one leads where they end.  Each
        # step takes the one way on that is not the way back; a chain that
        # forks, stops or loops is not a corridor and goes nowhere.
        def beyond(frm: int, first: int) -> int | None:
            prev, cur = frm, first
            for _ in range(64):
                if cur not in voids:
                    return cur
                onward = {t for t in voids[cur] if t != prev}
                if len(onward) != 1:
                    return None
                prev, cur = cur, onward.pop()
            return None

        collapsed = 0
        through: list[tuple] = []
        for frm, command, to, seen in edges:
            if to in voids:
                end = beyond(frm, to)
                if end is None:
                    continue
                collapsed += 1
                to = end
            through.append((frm, command, to, seen))
        edges = through

        # Edges last: every room exists by now, so a link to a room that was
        # never defined can be dropped rather than left dangling.
        known = {int(r["id"]) for r in db.execute("SELECT id FROM room")}
        good = [e for e in edges if e[2] in known and e[0] in known]
        for at in range(0, len(good), CHUNK):
            db.execute("BEGIN IMMEDIATE")
            try:
                db.executemany(
                    f"{verb} INTO edge "
                    "(from_room, command, to_room, seen, last_seen) "
                    "VALUES (?,?,?,0,?)", good[at:at + CHUNK])
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
    except Exception:
        if db.in_transaction:
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
            "folded": folded, "voids": collapsed, "unnamed": len(unnamed) - skipped}



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
#: An alias defined in the bot's own file, which its path then uses.  seal.tin
#: writes `.check_sarcophagus` thirteen times and defines it at the top.
BOT_OWN_ALIAS = re.compile(r"#alias\s*\{([.\w-]+)\}\s*\{(.*?)\n?\};", re.S)
#: tt++ inside a path.  Braced or bare -- 3kdb writes both: "#send {ptell
#: nofollow: pull brick;east}" and "#send !fly bike".
TT_SEND = re.compile(r"#send\s*(?:\{(.*?)\}|(\S.*?))\s*$", re.S)
TT_DELAY = re.compile(r"#delay\s+([\d.]+)\s*(?:\{(.*?)\}|(\S.*?))\s*$", re.S)
TT_REPEAT = re.compile(r"#(\d+)\s+(?:\{(.*?)\}|(\S.*?))\s*$", re.S)


def _own_aliases(text: str) -> dict[str, str]:
    """The aliases a bot file defines for its own path to use."""
    out = {}
    for name, body in BOT_OWN_ALIAS.findall(text):
        commands = [c.strip() for c in body.replace("\n", ";").split(";") if c.strip()]
        if commands and not any(c.startswith(("#", "$")) for c in commands):
            out[name.lower()] = ";".join(commands)
    return out


def translate_step(step: str, aliases: dict[str, str]) -> tuple[str, str]:
    """One path step as this client can run it, and what was left out.

    3kdb's paths are tt++ scripts, and four things in them are not commands
    the MUD would understand:

    * an alias the bot file defines itself -- put in where it is used;
    * `#send {x}`, which is tt++ for "send x without reading it as a
      command" -- so x, unwrapped;
    * `#delay N {x}`, which waits N seconds and then does x.  In a path,
      read in order, that is a wait followed by the commands -- and `wait N`
      is a step this client's walker honours;
    * `#N {x}`, tt++ for x N times.

    `.pause` is the fifth and has no equivalent: it is 3kdb stopping its own
    bot so you can do something by hand.  It comes out, and is reported, so
    a route that wanted you to step in does not look as though it ran clean.
    """
    from .botstore import Route
    parts, left_out = [], []
    # Brace-aware: the `;` in "#send {ptell nofollow: pull brick;east}" is part
    # of the party-tell message, not a break between two commands.  Splitting
    # through it sent "{ptell nofollow: pull brick" and then "east}".
    for part in (p.strip() for p in Route._split(step)):
        if not part:
            continue
        low = part.lower()
        if low in aliases:
            parts.append(aliases[low])
            continue
        if low.startswith(".pause"):
            left_out.append(part)
            continue
        got = TT_DELAY.match(part)
        if got:
            body = got.group(2) if got.group(2) is not None else (got.group(3) or "")
            parts.append(f"wait {float(got.group(1)):g}")
            if body.strip():
                parts.append(body.strip())
            continue
        got = TT_SEND.match(part)
        if got:
            body = (got.group(1) if got.group(1) is not None
                    else (got.group(2) or "")).strip()
            # A path step's semicolons always separate commands, so one
            # command that contains a semicolon cannot be written here:
            # sopem's "#send {ptell nofollow: pull brick;east}" is a single
            # party tell whose text has a semicolon in it.  Left out whole
            # rather than broken in half -- it is courtesy to a party, and
            # the walk does not depend on it.
            if ";" in body:
                left_out.append(part)
            elif body:
                parts.append(body)
            continue
        got = TT_REPEAT.match(part)
        if got:
            body = got.group(2) if got.group(2) is not None else (got.group(3) or "")
            if body.strip():
                parts.extend([body.strip()] * min(int(got.group(1)), 99))
            continue
        # 3kdb's own typo: seal.tin writes "e.check_sarcophagus" where it
        # means "e;.check_sarcophagus", and a direction glued to an alias is
        # neither.  Only split where the tail really is an alias this file
        # defines, so an ordinary command with a dot in it is left alone.
        head, dot, tail = part.partition(".")
        if dot and head and ("." + tail).lower() in aliases:
            parts.append(head)
            parts.append(aliases["." + tail.lower()])
            continue
        if part.startswith((".", "#")):
            left_out.append(part)          # a 3kdb alias this file does not define
            continue
        parts.append(part)
    return ";".join(parts), ";".join(left_out)


def translate_path(walk: str, text: str) -> tuple[str, list[str]]:
    """A whole `bot[path]` as this client can walk it, and what came out."""
    from .botstore import Route
    aliases = _own_aliases(text)
    out, left_out = [], []
    for step in Route(name="x", path=walk).steps():
        done, gone = translate_step(step, aliases)
        if done:
            out.append("{" + done + "}" if ";" in done else done)
        if gone:
            left_out.append(gone)
    return ";".join(out), left_out
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
    # 3kdb's path is a tt++ script; this is the walkable reading of it.
    walk, left_out = translate_path(walk, text)
    mobs = BOT_MOB.findall(text)
    setup = [m.group(1).strip() for line in text.splitlines()
             if (m := BOT_SETUP.match(line)) and m.group(1).strip() != "close"]
    return {
        "path": walk,
        #: steps 3kdb meant for itself, which are not in the path above
        "left_out": left_out,
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
    #: routes that walk, but with a step of 3kdb's own left out of them
    partial: dict[str, list[str]] = {}
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
            # 3kdb's own tags, as a folder: "chaos, dungeon" files 21 of its
            # bots under chaos/dungeon and 46 more under chaos.  The other 78
            # have no tags and start at the top, for the player to file.
            "group": "/".join(p.strip() for p in got["tags"].split(",")
                              if p.strip()),
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
        if data["left_out"]:
            partial[name] = data["left_out"]
        if note:
            note(f"  {name:<22} {len(route.steps()):>4} steps  "
                 f"{len(route.targets):>2} targets  start #{route.start}"
                 f"  {desc[:36]}")
    if note and partial:
        # Said rather than counted.  These routes walk, but somewhere in each
        # of them 3kdb stopped its own bot for the player to do something,
        # and a route that quietly walks past that is worth a warning.
        note(f"{len(partial)} route(s) have a step of 3kdb's own left out:")
        for name in sorted(partial):
            note(f"  {name:<22} {', '.join(partial[name])[:60]}")
    return {"added": added, "kept": kept, "skipped": skipped, "missing": "",
            "partial": {k: list(v) for k, v in partial.items()}}


def import_speedruns(store, path: str | Path) -> tuple[int, list[str]]:
    """Load ``.add_speedrun {name} {type} {vnum} {description}`` entries.

    Returns how many landed and the names of the ones that point at rooms this
    map does not have.
    """
    db = store.db
    known = {int(r["id"]) for r in db.execute("SELECT id FROM room")}
    added, missing = 0, []
    db.execute("BEGIN IMMEDIATE")
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
