"""Client commands -- the "/" verbs.

Shared by the console and the browser so the two cannot drift apart.  These
never reach the MUD; typing /js used to send it to 3K as a game command.
"""

from __future__ import annotations

from datetime import datetime

from . import events

HELP = [
    ("/help", "this list"),
    ("/js", "re-send the 3klient handshake"),
    ("/state", "parsed player state and code tally"),
    ("/clock", "tick source, period and queue depth"),
    ("/flush", "drop everything the scripts have queued"),
    ("/scripts", "loaded scripts, hook counts and errors"),
    ("/reload", "rescan the scripts directory now"),
    ("/test <line>", "feed a line through the triggers as if the MUD sent it"),
    ("/triggers", "every registered trigger and its prefilter literal"),
    ("/find <text>", "search everything this client has ever logged"),
    ("/here", "where the map thinks you are, and what leads out"),
    ("/name <text>", "rename the room you are in (blank clears it)"),
    ("/lost", "tell the map it has you in the wrong place"),
    ("/merge <id>", "fold room <id> into the one you are standing in"),
    ("/go <name>", "walk to the nearest mapped room with that name"),
    ("/region <name>", "label the area you are standing in"),
    ("/region under <name>", "nest this area inside another"),
    ("/region only <name>", "label just this room"),
    ("/regions", "the areas known, as a tree"),
    ("/bind <where>", "say which room you are in, by landmark or number"),
    ("/marks [text]", "named destinations imported from tt++"),
    ("/prefixes", "show the character settings that mark up 3K's output"),
    ("/prefixes set", "send them"),
    ("/lock", "stop the map growing (an imported map is finished)"),
    ("/unlock", "let it add rooms again"),
    ("/new", "rooms found that the imported map did not have"),
    ("/forget <id>", "remove a room the map should not have"),
    ("/dupes", "rooms that look like the same place twice"),
    ("/repair", "drop one-off readings that contradict a room"),
    ("/bots", "routes and hunts that are running"),
    ("/stop", "stop every bot at once"),
    ("/tick <secs> <command>", "send it every so often, and keep doing it"),
    ("/ticks", "the ones that are running"),
    ("/untick <name|all>", "stop one, or all of them"),
    ("/delay <secs> <command>", "send it once, later"),
]


def handle(text: str, session, scripts, note) -> bool:
    """Run a "/" command.  Returns False if it wasn't one of ours."""
    if not text.startswith("/"):
        return False

    verb, _, rest = text[1:].strip().partition(" ")
    verb, rest = verb.lower(), rest.strip()

    if verb in ("help", "?"):
        note("\n".join(f"  {v:<14} {d}" for v, d in HELP))

    elif verb in ("js", "jumpstart"):
        session.jumpstart()
        note(f"sent 3klient {session.sec_code}~{session.version}")

    elif verb == "state":
        p = session.world.player
        note(f"hp {p.hp}/{p.max_hp}  sp {p.sp}/{p.max_sp}  "
             f"gp1 {p.gp1}/{p.max_gp1}  round {p.__dict__.get('round')}\n"
             f"  enemy {p.enemy!r} at {p.enemy_pct}%\n"
             f"  room {session.world.room.short!r} exits {session.world.room.exits}\n"
             f"  guild {({k: v.value for k, v in p.gline.items()})}\n"
             f"  codes {dict(session.codes_seen)}"
             + (f"\n  \x1b[31mnot being sent: "
                f"{', '.join(session.mip_quiet())}\x1b[0m"
                if session.mip_quiet() else ""))

    elif verb == "clock":
        c = session.clock
        a = session.apm
        note(f"tick source={c.source} period={c.period:.2f}s ticks={c.ticks}\n"
             f"  apm {a.rate()}/{a.limit} (throttles at {a.soft}) "
             f"queued={len(session.queue)} sent={session.queue.sent}")

    elif verb in ("flush", "stop"):
        note(f"dropped {session.queue.flush()} queued command(s)")

    elif verb == "scripts":
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        else:
            lines = []
            for name, reg in sorted(scripts.registries.items()):
                lines.append(
                    f"  {name:<16} {len(reg.handlers)} event, {len(reg.watches)} watch, "
                    f"{reg.triggers} trigger, {len(scripts.aliases.candidates(''))} alias, "
                    f"{len(reg.periodics)} timer")
            for name, err in sorted(scripts.errors.items()):
                lines.append(f"  \x1b[31m{name}: {err.strip().splitlines()[-1]}\x1b[0m")
            note("\n".join(lines) or f"no scripts in {scripts.dir}/")

    elif verb == "reload":
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        else:
            changed = scripts.reload_changed()
            note(f"reloaded: {', '.join(changed) if changed else 'nothing changed'}")

    elif verb in ("triggers", "aliases"):
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        else:
            which = scripts.aliases if verb == "aliases" else scripts.triggers
            rows = [
                f"  [{t.owner}] {t.mode:<8} {t.pattern!r}"
                + (f"   prefilter={t.literal!r}" if t.literal else "   (always checked)")
                for t in which.all()
            ]
            note("\n".join(rows) or f"no {verb} registered")

    elif verb == "test":
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        elif not rest:
            note("usage: /test <a line as the MUD would send it>")
        else:
            hits = scripts.triggers.fire(rest)
            note(f"{len(hits)} trigger(s) matched {rest!r}"
                 + "".join(f"\n  [{t.owner}] {t.pattern!r} -> {c}" for t, c in hits))
            session.bus.emit(events.LINE, rest, rest)

    elif verb == "find":
        _find(session, rest, note)

    elif verb == "here":
        _here(session, note)

    elif verb in ("name", "lost", "merge"):
        _correct(session, verb, rest, note)

    elif verb == "go":
        _go(session, rest, note)

    elif verb == "region":
        _region(session, rest, note)

    elif verb == "regions":
        _regions(session, note)

    elif verb == "bind":
        _bind(session, rest, note)

    elif verb == "prefixes":
        _prefixes(session, rest, note)

    elif verb == "marks":
        store = getattr(session, "store", None)
        if store is None:
            note("mapping is off (--no-map)")
        else:
            found = store.landmarks(rest, limit=40)
            note("\n".join(f"  {m['name']:<18} {(m['kind'] or ''):<9} "
                            f"{(m['note'] or '')[:48]}" for m in found)
                 or f"no landmarks matching {rest!r}")

    elif verb in ("lock", "unlock"):
        store = getattr(session, "store", None)
        if store is None:
            note("mapping is off (--no-map)")
        else:
            store.locked = verb == "lock"
            note("the map will not add rooms; unrecognised ones leave it "
                 "lost instead" if store.locked
                 else "the map will add rooms it does not recognise")

    elif verb == "new":
        store = getattr(session, "store", None)
        if store is None:
            note("mapping is off (--no-map)")
        else:
            from .mapper import NEW
            found = store.tagged(NEW)
            note("\n".join(
                f"  #{r['id']:<6} {(r['name'] or 'unnamed')[:34]:<34} "
                f"visits {r['visits']}" for r in found)
                or "nothing found that the map did not already have")

    elif verb == "forget":
        store = getattr(session, "store", None)
        if store is None or not rest.isdigit():
            note("usage: /forget <room id>   (ids show when you hover the map)")
        elif store.room(int(rest)) is None:
            note(f"no room {rest}")
        else:
            gone = store.room(int(rest))["name"]
            if session.mapper and session.mapper.here == int(rest):
                session.mapper.here = None
            store.forget(int(rest))
            note(f"forgot #{rest} {gone!r}")

    elif verb == "dupes":
        _dupes(session, note)

    elif verb == "bots":
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        else:
            rows = scripts.bots.status()
            note("\n".join(
                f"  {b['name']:<16} {'running' if b['running'] else 'stopped':<8}"
                f" {b['steps']:>4} steps  {b['kills']:>3} kills"
                f"  [{b['owner']}] {b['note']}"
                for b in rows) or "no bots")

    elif verb == "stop":
        if scripts is None:
            note("scripting is disabled (--no-scripts)")
        else:
            n = scripts.bots.stop_all()
            session.queue.flush()
            note(f"stopped {n} bot(s), queue cleared")

    elif verb in ("tick", "ticks", "untick"):
        _tick(session, verb, rest, scripts, note)

    elif verb == "delay":
        _delay(session, rest, note)

    elif verb == "repair":
        store = getattr(session, "store", None)
        if store is None:
            note("mapping is off (--no-map)")
        else:
            from .tintin import walkable

            gone = store.prune_fingerprints()
            said = [f"dropped {len(gone)} stray reading(s)"
                    + "".join(f"\n  room {r}: [{e}]" for r, e in gone)] if gone else []
            # Two things an older import left behind: exits carrying TinTin++
            # directives, which this client would type at the MUD, and exits
            # that are the same way out spelled with and without a space.
            scrubbed = store.clean_edge_commands(walkable)
            if scrubbed:
                said.append(f"took TinTin++ out of {scrubbed} exit(s)")
            folded = store.fold_spaced_exits()
            if folded:
                said.append(f"folded {folded} exit(s) written two ways")
            note("\n".join(said) if said else "nothing to repair")

    else:
        note(f"unknown command /{verb} -- try /help")

    return True


def _find(session, query: str, note) -> None:
    """Search the log.  Results are newest first, with the room they happened
    in, because "where" is usually half of what you are trying to remember."""
    store = getattr(session, "store", None)
    if store is None:
        note("logging is off (--no-map)")
        return
    if not query:
        note("usage: /find <text>   e.g. /find belochs")
        return
    if session.logbook is not None:
        session.logbook.flush()          # include what was said a moment ago

    hits = store.search(query, limit=25)
    if not hits:
        note(f"nothing logged matching {query!r}")
        return

    names = {}
    rows = []
    for line in reversed(hits):          # oldest first reads like a transcript
        when = datetime.fromtimestamp(line["at"]).strftime("%d %b %H:%M")
        room = line["room_id"]
        if room is not None and room not in names:
            row = store.room(room)
            names[room] = (row["name"] if row and row["name"] else f"room {room}")
        where = f"  [{names[room]}]" if room is not None else ""
        arrow = ">" if line["kind"] == "sent" else " "
        rows.append(f"  {when} {arrow} {line['text']}{where}")
    note(f"{len(hits)} match(es) for {query!r}:\n" + "\n".join(rows))


def _here(session, note) -> None:
    mapper = getattr(session, "mapper", None)
    if mapper is None:
        note("mapping is off (--no-map)")
        return
    state = mapper.status()
    if state["lost"]:
        note(f"lost -- {state['candidates']} room(s) look like this one; "
             f"walk somewhere and it will settle")
        return
    walked = ", ".join(f"{c} -> {r}" for c, r in state["exits"].items()) or "none"
    unwalked = [e for e in session.store.exits_of(state["room"])
                if e not in state["exits"]]
    note(f"room {state['room']}: {state['name'] or 'unnamed'}"
         + (f"  ({' > '.join(state['region'])})" if state["region"] else "")
         + f"\n  visits {state['visits']}"
         + f"\n  walked: {walked}"
         + f"\n  unwalked: {', '.join(unwalked) or 'none'}"
         + f"\n  map holds {state['edges']} edges")


def _correct(session, verb: str, rest: str, note) -> None:
    """Corrections.

    Dead reckoning is inference, and inference is sometimes wrong: a missed
    move splits one room into two, a laggy tick hangs the wrong name on a
    place.  Nothing detects that but you, so the map has to be correctable
    or its mistakes are permanent.
    """
    mapper = getattr(session, "mapper", None)
    if mapper is None:
        note("mapping is off (--no-map)")
        return
    store = session.store

    if verb == "lost":
        # Not a room to delete -- the room is real, we are just not in it.
        mapper.unsure()
        note("map is now unsure where you are; walk somewhere and it will "
             "work it out")
        return

    if mapper.here is None:
        note("the map does not know where you are -- walk a room first")
        return

    if verb == "name":
        store.rename(mapper.here, rest or None)
        note(f"room {mapper.here} is now {rest!r}" if rest
             else f"room {mapper.here} has no name again")
        return

    try:
        other = int(rest)
    except ValueError:
        note("usage: /merge <room id>   (ids show when you hover the map)")
        return
    if store.room(other) is None:
        note(f"no room {other}")
        return
    store.merge(mapper.here, other)
    note(f"room {other} folded into {mapper.here}")


def _bind(session, rest: str, note) -> None:
    """Say which room you are standing in, by landmark or by number.

    An imported map is a world with no idea where you are in it.  One anchor
    is all dead reckoning needs; after that it follows the imported exits the
    same way it follows ones you walked yourself.
    """
    mapper = getattr(session, "mapper", None)
    if mapper is None:
        note("mapping is off (--no-map)")
        return
    store = session.store
    if not rest:
        note("usage: /bind <room number>  or  /bind <landmark>")
        return

    if rest.isdigit() and store.room(int(rest)) is not None:
        room = int(rest)
    else:
        mark = store.landmark(rest)
        if mark is None:
            note(f"no landmark or room {rest!r}")
            return
        room = int(mark["room_id"])

    mapper.here, mapper.candidates = room, []
    row = store.room(room)
    note(f"you are in #{room} {row['name'] or 'unnamed'}"
         + (f"  ({' > '.join(store.region_path(room))})"
            if store.region_path(room) else ""))


def _tick(session, verb: str, rest: str, scripts, note) -> None:
    """Timers, in the shape tt++ players already have in their fingers.

    A timer is a rule like any other -- stored with the character, editable in
    the panel, and paced by the same governor -- so "/tick 290 xp" is a way of
    writing one rather than a second mechanism that does the same job.
    """
    store = getattr(scripts, "rules", None)
    if store is None:
        note("scripting is disabled (--no-scripts)")
        return
    from .rules import MIN_EVERY, Rule

    timers = [r for r in store.rules if r.kind == "timer"]

    if verb == "ticks" or (verb == "tick" and not rest.strip()):
        if not timers:
            note("no timers.  /tick 290 xp sends xp every 290 seconds.")
            return
        note("\n".join(
            f"  {'on ' if t.enabled else 'off'} every {float(t.every):g}s  "
            f"{t.name or '(unnamed)'}  "
            + " ; ".join(a['text'] for a in t.actions)
            for t in timers))
        return

    if verb == "untick":
        want = rest.strip().lower()
        if not want:
            note("usage: /untick <name>   or   /untick all")
            return
        doomed = (timers if want == "all"
                  else [t for t in timers if t.name.lower() == want
                        or any(a["text"].lower() == want for a in t.actions)])
        if not doomed:
            note(f"no timer called {rest.strip()!r} -- /ticks lists them")
            return
        for t in doomed:
            store.rules.remove(t)
        store.save()
        store.register()
        note(f"stopped {len(doomed)} timer(s)")
        return

    secs, _, command = rest.strip().partition(" ")
    try:
        every = float(secs)
    except ValueError:
        note("usage: /tick <seconds> <command>   e.g. /tick 290 xp")
        return
    if not command.strip():
        note("usage: /tick <seconds> <command>   e.g. /tick 290 xp")
        return
    if every < MIN_EVERY:
        note(f"{every:g}s is faster than the game beat; "
             f"{MIN_EVERY:g}s is the shortest that means anything")
        return

    # Named after what it sends, so "/untick xp" works without anyone having
    # to name it, and setting the same tick twice replaces it rather than
    # stacking a second copy that nobody can see.
    name = command.strip()
    for old in [t for t in timers if t.name.lower() == name.lower()]:
        store.rules.remove(old)
    store.rules.append(Rule(kind="timer", name=name, every=every,
                            actions=[{"type": "send", "text": name}]))
    store.save()
    store.register()
    note(f"every {every:g}s: {name}   (/ticks to see them, /untick {name} to stop)")


def _delay(session, rest: str, note) -> None:
    """Send something once, later.  Nothing to store: it happens and is gone."""
    import asyncio

    secs, _, command = rest.strip().partition(" ")
    try:
        wait = float(secs)
    except ValueError:
        note("usage: /delay <seconds> <command>   e.g. /delay 5 quaff heal")
        return
    if not command.strip():
        note("usage: /delay <seconds> <command>   e.g. /delay 5 quaff heal")
        return

    async def later() -> None:
        await asyncio.sleep(wait)
        session.queue.put(command)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        note("not running yet")
        return
    asyncio.ensure_future(later())
    note(f"in {wait:g}s: {command}")


def _go(session, text: str, note) -> None:
    """Walk somewhere by name, for when it is not on screen to click."""
    mapper = getattr(session, "mapper", None)
    if mapper is None:
        note("mapping is off (--no-map)")
        return
    if not text:
        note("usage: /go <part of a room name>   e.g. /go center of town")
        return
    if mapper.here is None:
        note("the map does not know where you are -- walk a room first")
        return

    # Landmarks first: they are the names a player already types, and "beloch"
    # should mean the one room he means rather than every room mentioning it.
    mark = session.store.landmark(text)
    if mark is None:
        near = session.store.landmarks(text)
        mark = near[0] if len(near) == 1 else None
        if len(near) > 1:
            note("which one?\n" + "\n".join(
                f"  {m['name']:<16} {m['note'][:52]}" for m in near[:12]))
            return
    if mark is not None:
        room = int(mark["room_id"])
        route = mapper.route(room)
        if route is None:
            note(f"no route from here to {mark['name']}")
            return
        session.travel(room, "speedwalk")
        note(f"walking {len(route)} steps to {mark['name']} -- {mark['note']}"
             "\n  /bots to watch it, /stop to stop it")
        return

    matches = mapper.find_rooms(text)
    if not matches:
        note(f"no mapped room matching {text!r} that there is a way to "
             f"from here")
        return

    room, name, _ = matches[0]
    route = mapper.route(room)
    session.travel(room, "speedwalk")
    others = "".join(f"\n  also #{i} {n} ({d} steps)" for i, n, d in matches[1:4])
    note(f"walking {len(route)} steps to #{room} {name}{others}")


def _regions(session, note) -> None:
    store = getattr(session, "store", None)
    if store is None:
        note("mapping is off (--no-map)")
        return
    tree = store.region_tree()
    if not tree:
        note("no areas labelled yet -- stand in one and try /region <name>")
        return
    note("\n".join(f"  {'  ' * depth}{row['name']}  ({n} rooms)"
                    for depth, row, n in tree))


def _region(session, rest: str, note) -> None:
    """Label the area you are in.

    The default spreads: an area is a connected run of rooms, and labelling
    them one at a time is not something anybody would do twice.  It stops at
    exits with no direction to them and at rooms another area already claims,
    which is a proposal you can correct rather than a verdict.
    """
    mapper = getattr(session, "mapper", None)
    if mapper is None:
        note("mapping is off (--no-map)")
        return
    store = session.store

    if mapper.here is None:
        note("the map does not know where you are -- walk a room first")
        return
    if not rest:
        path = store.region_path(mapper.here)
        note(" > ".join(path) if path else "this room is not in any area")
        return

    mode, _, name = rest.partition(" ")
    mode, name = mode.lower(), name.strip()

    if mode == "under":
        if not name:
            note("usage: /region under <area>")
            return
        here = store.room(mapper.here)
        if here["region_id"] is None:
            note("label this area first: /region <name>")
            return
        parent = store.region_by_name(name)
        if parent is None:
            parent_id = store.add_region(name)
        else:
            parent_id = parent["id"]
        problem = store.reparent(here["region_id"], parent_id)
        note(problem or " > ".join(store.region_path(mapper.here)))
        return

    if mode == "only":
        if not name:
            note("usage: /region only <name>")
            return
        rooms, label = [mapper.here], name
    else:
        rooms, label = mapper.area(), rest.strip()

    existing = store.region_by_name(label)
    region_id = existing["id"] if existing else store.add_region(label)
    store.assign(rooms, region_id)
    note(f"{len(rooms)} room(s) are now {label!r}"
         + (f"  ({' > '.join(store.region_path(mapper.here))})"
            if store.region_path(mapper.here) else ""))


def _dupes(session, note) -> None:
    store = getattr(session, "store", None)
    if store is None:
        note("mapping is off (--no-map)")
        return
    found = store.duplicates()
    if not found:
        note("no rooms look like duplicates")
        return
    rows = []
    for what, ids in found:
        names = []
        for rid in ids:
            row = store.room(rid)
            names.append(f"#{rid} {row['name'] or 'unnamed'}"
                         if row else f"#{rid} (gone)")
        rows.append("  " + ", ".join(names) + f"\n      {what[:96]}")
    note(f"{len(found)} group(s) that may be one room each -- stand in the one "
         f"to keep and /merge the other:\n" + "\n".join(rows))


def _prefixes(session, rest: str, note) -> None:
    """Show or send the settings that mark up 3K's output.

    Showing first, always: these are commands going to somebody's character,
    and a button that fires thirteen of them unseen is a button nobody should
    press.
    """
    from .prefixes import Prefixes

    # The session's own copy, re-read: it is the one the markup reader and the
    # marker hider work from, so an edit has to reach it too or the client
    # would go on looking for markers the character no longer has.
    marks = getattr(session, "prefixes", None)
    if marks is None:
        marks = Prefixes(getattr(session, "prefixes_path",
                                 "scripts/prefixes.json"))
    elif hasattr(session, "reload_prefixes"):
        session.reload_prefixes()
    commands = marks.commands()

    if rest.strip().lower() not in ("set", "send", "go"):
        note("these are character settings, not mudlib changes -- they wrap "
             "each kind of line so the client can read it, and the client "
             "takes them back out before you see them.\n"
             + "\n".join(f"  {c}" for c in commands)
             + f"\n\nedit {marks.path} to change them, /prefixes set to send.")
        return

    for command in commands:
        session.queue.put(command)
    note(f"sent {len(commands)} settings; watch for the confirmations")
