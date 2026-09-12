"""Client commands -- the "/" verbs.

Shared by the console and the browser so the two cannot drift apart.  These
never reach the MUD; typing /js used to send it to 3K as a game command.
"""

from __future__ import annotations

from datetime import datetime

from . import events

#: The "/" verbs, grouped by what you are trying to do.  Grouped
#: because a flat list of thirty-odd commands is a list nobody reads,
#: and the browser renders these as a panel rather than a wall of
#: text in the terminal.
HELP = [
    ('Getting about', 'The map is 49,494 rooms somebody else walked, so most places already have a name you can go to.', [
        ('/go <name>', 'walk to the nearest mapped room with that name'),
        ('/here', 'where the map thinks you are, and what leads out'),
        ('/speedruns [word]', 'named places you can /go to, and how far'),
        ('/bind <where>', 'say which room you are in, by landmark or number'),
        ('/lost', 'tell the map it has you in the wrong place'),
        ('/regions', 'the areas known, as a tree'),
        ('/region <name>', 'label the area you are standing in'),
        ('/region under <name>', 'nest this area inside another'),
        ('/region only <name>', 'label just this room'),
    ]),
    ('Looking things up', 'Every session is logged and filed by the room it happened in.', [
        ('/find <text>', 'search everything this client has ever logged'),
        ('/state', 'parsed player state and code tally'),
        ('/clock', 'tick source, period and queue depth'),
    ]),
    ('Running things', 'Routes, and anything the scripts have started.', [
        ('/bots', 'routes and hunts that are running'),
        ('/stop', 'stop every bot at once'),
        ('/tick <secs> <command>', 'send it every so often, and keep doing it'),
        ('/ticks', 'the ones that are running'),
        ('/untick <name|all>', 'stop one, or all of them'),
        ('/delay <secs> <command>', 'send it once, later'),
        ('/group <name> on|off', 'switch a folder on or off, rules and routes; /groups lists them'),
        ('/folders', 'every folder, and what is filed in it'),
        ('/alias <word> <cmd;cmd>', 'make an alias; {args} or {1} for what follows it'),
        ('/alias', 'the aliases you have made; /alias <word> shows one'),
        ('/unalias <word>', 'remove one'),
        ('/flush', 'drop everything the scripts have queued'),
    ]),
    ('Gags', 'Lines kept off the screen -- also under Options -> Gags. Your triggers and the log still see them.', [
        ('/gag <text>', 'hide every line containing it'),
        ('/gags', 'the ones in force'),
        ('/ungag <text>', 'show it again; /ungag all for every one'),
    ]),
    ('Scripting', 'Rules written as Python, reloaded as you save them.', [
        ('/scripts', 'loaded scripts, hook counts and errors'),
        ('/reload', 'rescan the scripts directory now'),
        ('/test <line>', 'feed a line through the triggers as if the MUD sent it'),
        ('/triggers', 'every registered trigger and its prefilter literal'),
    ]),
    ('Correcting the map', "It is yours to fix; nothing here touches anybody else's copy.", [
        ('/name <text>', 'rename the room you are in (blank clears it)'),
        ('/merge <id>', 'fold room <id> into the one you are standing in'),
        ('/forget <id>', 'remove a room the map should not have'),
        ('/new', 'rooms found that the imported map did not have'),
        ('/dupes', 'rooms that look like the same place twice'),
        ('/repair', 'drop one-off readings that contradict a room'),
        ('/mapsum', 'a summary of your map, to send somebody'),
        ('/mapcheck <file>', "compare a summary somebody sent with your own"),
        ('/lock', "stop the map growing (it is 3kdb's, and locked from the start)"),
        ('/unlock', 'let it add rooms, for mapping somewhere 3kdb does not cover'),
    ]),
    ('The connection', '', [
        ('/js', 're-send the 3klient handshake'),
        ('/prefixes', "show the character settings that mark up 3K's output"),
        ('/prefixes set', 'send them'),
        ('/ansivars', 'read and keep your own colour settings from 3K'),
        ('/ansivars restore', 'show what would put them back'),
        ('/ansivars restore go', 'send it'),
        ('/help', 'this list'),
        ('/help <topic>', 'read the guide: /help triggers, /help regex, /help routes...'),
    ]),
]


def stack(line: str) -> list[str]:
    """One typed line as the commands it holds: `n;w;n;n;e;n` is six.

    Each piece then goes where a typed line would -- an alias, a client
    command, or 3K -- so `n;/go bank` works.  `\\;` is a semicolon that stays
    in the command (`say hi\\; bye`).  A line that starts with `/` is left
    whole: it is the client's, and its own `;` belong to it --
    `/alias gk kill {1};glance`.  A line with no `;` is not touched at all,
    spaces and all, and an empty one is still one empty command: Enter on
    nothing is how you ask 3K for a prompt.
    """
    if line.startswith("/") or ";" not in line:
        return [line]
    pieces = [p.replace("\x00", ";").strip()
              for p in line.replace("\\;", "\x00").split(";")]
    return [p for p in pieces if p] or [""]


def handle(text: str, session, scripts, note) -> bool:
    """Run a "/" command.  Returns False if it wasn't one of ours."""
    if not text.startswith("/"):
        return False

    verb, _, rest = text[1:].strip().partition(" ")
    verb, rest = verb.lower(), rest.strip()

    if verb in ("help", "?"):
        from . import guide

        if rest:
            # A topic of the guide, by name or by a word in it.
            found = guide.find(rest)
            if not found:
                note(f"nothing in the guide about {rest!r}.  " + guide.index())
            elif len(found) == 1 or found[0]["id"] == rest.strip().lower():
                note(guide.plain(found[0]))
            else:
                note(f"{rest!r} is in: " + ", ".join(
                    f"{t['id']} ({t['title']})" for t in found[:8])
                    + f"\n/help {found[0]['id']} to read one.")
            return True
        wide = max(len(v) for _t, _b, rows in HELP for v, _d in rows)
        out = []
        for title, _blurb, rows in HELP:
            out.append(f"\n  {title}")
            out += [f"    {v:<{wide}}  {d}" for v, d in rows]
        out.append("\n" + guide.index())
        note("\n".join(out).lstrip("\n"))

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

    elif verb == "flush":
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

    elif verb == "ansivars":
        _ansivars(session, rest, note)

    elif verb in ("speedruns", "runs", "marks"):
        _speedruns(session, rest, note)

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
        # This used to sit below an earlier `verb in ("flush", "stop")`, which
        # took it: /stop emptied the queue and left every bot walking.
        if scripts is None:
            note(f"dropped {session.queue.flush()} queued command(s)")
        else:
            n = scripts.bots.stop_all()
            session.queue.flush()
            rules = getattr(scripts, "rules", None)
            held = rules.cancel_waits() if rules is not None else 0
            note(f"stopped {n} bot(s), queue cleared"
                 + (f", {held} waiting rule(s) dropped" if held else ""))

    elif verb in ("tick", "ticks", "untick"):
        _tick(session, verb, rest, scripts, note)

    elif verb in ("gag", "gags", "ungag"):
        _gag(verb, rest, scripts, note)

    elif verb == "delay":
        _delay(session, rest, note)

    elif verb in ("mapsum", "mapcheck"):
        _mapsum(verb, rest, session, note)

    elif verb in ("group", "groups"):
        _group(rest, scripts, note)

    elif verb in ("folder", "folders"):
        _folders(rest, scripts, note)

    elif verb in ("alias", "unalias"):
        _alias(verb, rest, scripts, note)

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
    from .rules import MIN_EVERY, Rule, describe

    timers = [r for r in store.rules if r.kind == "timer"]

    if verb == "ticks" or (verb == "tick" and not rest.strip()):
        if not timers:
            note("no timers.  /tick 290 xp sends xp every 290 seconds.")
            return
        note("\n".join(
            f"  {'on ' if t.enabled else 'off'} every {float(t.every):g}s  "
            f"{t.name or '(unnamed)'}  "
            + " ; ".join(describe(a) for a in t.actions)
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
    from .events import spawn
    spawn(later(), f"/delay {command}")
    note(f"in {wait:g}s: {command}")


def by_group(rules, show) -> str:
    """Rules listed under their groups, the ungrouped last, as the panel does.

    With no groups at all, just the rules.
    """
    key = lambda r: (r.pattern or r.name or "").lower()      # noqa: E731
    groups: dict[str, list] = {}
    loose = []
    for r in rules:
        if r.group:
            groups.setdefault(r.group.lower(), []).append(r)
        else:
            loose.append(r)
    if not groups:
        return "\n".join(show(r) for r in sorted(loose, key=key))
    out = []
    for name in sorted(groups):
        members = groups[name]
        out.append(f"{members[0].group}:")
        out.extend(show(r) for r in sorted(members, key=key))
    if loose:
        out.append("no group:")
        out.extend(show(r) for r in sorted(loose, key=key))
    return "\n".join(out)


def _alias_actions(text: str) -> list[dict]:
    """`recall;n;/wait 2;n` -> a send for each, and `/wait 2` a wait."""
    actions = []
    for piece in (p.strip() for p in text.split(";")):
        if not piece:
            continue
        verb, _, arg = piece.partition(" ")
        if verb.lower() == "/wait":
            actions.append({"type": "wait", "text": arg.strip()})
        else:
            actions.append({"type": "send", "text": piece})
    return actions


def _alias(verb: str, rest: str, scripts, note) -> None:
    """An alias made from the input line, as tt++'s #alias does.

    It is an ordinary alias rule -- the word you type, matched as a command,
    so `{args}` is everything after it and `{1}` the first word -- stored with
    the character and editable under Options -> Aliases.  Setting a word
    again changes what it does rather than making a second one; anything the
    form gave it, a group say, is kept.
    """
    store = getattr(scripts, "rules", None)
    if store is None:
        note("scripting is disabled (--no-scripts)")
        return
    from .rules import describe

    def mine():
        return [r for r in store.rules if r.kind == "alias" and r.mode == "command"]

    def show(r) -> str:
        return (f"  {'   ' if r.enabled else 'off'} {r.pattern:<14} "
                + " ; ".join(describe(a) for a in r.actions))

    word, _, commands_ = rest.strip().partition(" ")
    found = [r for r in mine() if r.pattern.lower() == word.lower()] if word else []

    if verb == "unalias":
        if not word:
            note("usage: /unalias <word>")
        elif not found:
            note(f"no alias {word!r} -- /alias lists them")
        else:
            for r in found:
                store.delete(r.id)
            note(f"removed the alias {word}")
        return

    if not word:
        note(by_group(mine(), show)
             or "no aliases.  /alias <word> <command;command> makes one, "
                "e.g. /alias gk kill {1};glance")
        return
    if not commands_.strip():
        note(show(found[0]) + (f"   (group {found[0].group})" if found[0].group else "")
             if found else f"no alias {word!r}")
        return
    if word.startswith("/"):
        note("an alias cannot start with / -- those are the client's commands")
        return

    data = {"kind": "alias", "mode": "command", "pattern": word, "name": word,
            "actions": _alias_actions(commands_)}
    if found:
        from dataclasses import asdict
        data = {**asdict(found[0]), "actions": data["actions"]}
    rule, problem = store.upsert(data)
    if problem:
        note(f"/alias {word}: {problem}")
        return
    note(f"{'changed' if found else 'new'} alias {rule.pattern}: "
         + " ; ".join(describe(a) for a in rule.actions))


def _mapsum(verb: str, rest: str, session, note) -> None:
    """Your map in a line, and the same from somebody else.

    Two players cannot hand each other a map -- tens of megabytes, and the
    file holds that player's session log as well.  A summary is counts,
    digests and area names, and nothing else, so it is safe to send.
    """
    from pathlib import Path

    from . import mapsum
    from .paths import home

    store = getattr(session, "store", None)
    if store is None:
        note("mapping is off (--no-map)")
        return
    if verb == "mapsum":
        got = mapsum.summarize(store)
        where = Path(rest.strip()) if rest.strip() else home() / "map-summary.json"
        try:
            mapsum.write(where, got)
            said = f"written to {where} -- send that file, and they run /mapcheck on it"
        except OSError as exc:
            said = f"could not write it to {where}: {exc}"
        note("\n".join(mapsum.lines(got) + ["  " + said]))
        return
    if not rest.strip():
        note("usage: /mapcheck <file>   the summary somebody sent you (/mapsum writes yours)")
        return
    try:
        theirs = mapsum.read(Path(rest.strip()).expanduser())
    except (OSError, ValueError) as exc:
        note(f"could not read {rest.strip()}: {exc}")
        return
    note("\n".join(mapsum.compare(mapsum.summarize(store), theirs)))


def _group(rest: str, scripts, note) -> None:
    """Rules switched on and off together, as tt++'s #class does.

    A group is only a name on each rule, set in the rule's form, so there is
    nothing to create: `/group party on` switches on every rule named party,
    and an alias whose actions are `/group solo off` and `/group party on`
    is a mode.
    """
    store = getattr(scripts, "rules", None)
    if store is None:
        note("scripting is disabled (--no-scripts)")
        return
    groups = store.groups()

    def state(rules) -> str:
        on = sum(1 for r in rules if r.enabled)
        return ("on" if on == len(rules) else "off" if not on
                else f"{on} of {len(rules)} on")

    words = rest.split()
    if not words:
        note("\n".join(f"  {name:<16} {state(rules):<10} {len(rules)} rule(s)"
                        for name, rules in sorted(groups.items(), key=lambda g: g[0].lower()))
             or "no groups.  Give rules a group in their form, then /group <name> on|off.")
        return
    switch = words[-1].lower() if words[-1].lower() in ("on", "off") else None
    name = " ".join(words[:-1] if switch else words)
    known = {g.lower(): g for g in groups}
    if name.lower() not in known:
        note(f"no rules in a group called {name!r}"
             + (f" -- there are: {', '.join(sorted(groups))}" if groups else ""))
        return
    name = known[name.lower()]
    if switch is None:
        from .rules import describe

        def what(r) -> str:
            said = (r.pattern if r.kind in ("trigger", "alias")
                    else f"on {r.event}" if r.kind == "event"
                    else f"every {float(r.every):g}s" if r.kind == "timer"
                    else f"{r.watch_field} {r.op} {r.value}")
            return (f"  {'   ' if r.enabled else 'off'} {r.kind:<8} {said:<24} "
                    + " ; ".join(describe(a) for a in r.actions))
        note(f"{name}: {state(groups[name])}\n"
             + "\n".join(what(r) for r in groups[name]))
        return
    # A folder is one name across both stores, so switching it here switches
    # its routes too -- otherwise `/group zodiacs off` leaves the area's route
    # still walking, which is not what anybody means by it.
    did = scripts.set_folder(name, switch == "on")
    said = f"{did['rules']} rule(s)"
    if did.get("routes"):
        said += f" and {did['routes']} route(s)"
    note(f"{name}: {said} {switch}")


def _folders(rest: str, scripts, note) -> None:
    """Every folder, with what is filed in it across both stores.

    `/groups` lists the rule groups; this is the same names read as folders,
    counting the routes as well, which is the whole point of a folder over a
    group.  `/folders <name>` is `/group <name>`, which already lists one.
    """
    if scripts is None:
        note("scripting is disabled (--no-scripts)")
        return
    if rest.strip():
        _group(rest, scripts, note)
        return
    rows = scripts.folders()
    if not rows:
        note("no folders.  Put a name in the Folder box of a trigger, an "
             "alias, a timer or a route, and it is one.")
        return
    order = ("trigger", "alias", "event", "watch", "timer", "route")

    def what(kinds: dict) -> str:
        return ", ".join(f"{kinds[k]} {k}" + ("" if kinds[k] == 1 else "s")
                         for k in order if kinds.get(k))
    note("\n".join(
        f"  {row['path']:<22} {('on' if row['on'] == row['count'] else 'off' if not row['on'] else str(row['on']) + ' of ' + str(row['count']) + ' on'):<12} {what(row['kinds'])}"
        for row in rows))


def _gag(verb: str, rest: str, scripts, note) -> None:
    """Lines kept off the screen, the way tt++'s #gag does it.

    A gag is kept as a rule -- a trigger with its gag box ticked and nothing
    else to do -- so it is stored with the character, but it is listed under
    Options -> Gags, not among the triggers: a line to hide is not something
    that reacts.  Contains, and case matters, which is what #gag means.
    """
    store = getattr(scripts, "rules", None)
    if store is None:
        note("scripting is disabled (--no-scripts)")
        return
    from .rules import Rule, describe

    gags = [r for r in store.rules if r.kind == "trigger" and r.gag]
    text = rest.strip()

    if verb == "gags" or (verb == "gag" and not text):
        if not gags:
            note("no gags.  /gag <text> hides every line containing it.")
            return
        note("\n".join(
            f"  {'on ' if g.enabled else 'off'} {g.mode:<8} {g.pattern}"
            + (f"   (also: {' ; '.join(describe(a) for a in g.actions)})"
               if g.actions else "")
            for g in gags))
        return

    if verb == "ungag":
        if not text:
            note("usage: /ungag <text>   or   /ungag all")
            return
        doomed = gags if text.lower() == "all" else [
            g for g in gags if g.pattern == text or (g.name and g.name == text)]
        if not doomed:
            note(f"no gag on {text!r} -- /gags lists them")
            return
        for g in doomed:
            if g.actions:
                g.gag = False             # still a trigger; only stop hiding
            else:
                store.rules.remove(g)
        store.save()
        store.register()
        note(f"showing {len(doomed)} again")
        return

    if any(g.pattern == text and g.mode == "contains" for g in gags):
        note(f"already hiding lines containing {text!r}")
        return
    store.rules.append(Rule(kind="trigger", pattern=text, mode="contains",
                            gag=True, actions=[]))
    store.save()
    store.register()
    note(f"hiding lines containing {text!r} -- /ungag {text} to show them")


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
        # A look is cheaper and safer than the walk this used to ask for, and
        # it is how the map finds itself again: one room's exits and scenery
        # are usually a unique fingerprint.  If it does find us, the /go goes
        # ahead from there rather than making the player type it twice.
        note("the map does not know where you are -- looking first")
        events.spawn(_look_then_go(session, text, note), "finding where we are")
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
        session.travel(room, "speedwalk", mark["name"])
        note(f"walking {len(route)} steps to {mark['name']} -- {mark['note']}")
        return

    matches = mapper.find_rooms(text)
    if not matches:
        note(f"no mapped room matching {text!r} that there is a way to "
             f"from here")
        return

    room, name, _ = matches[0]
    route = mapper.route(room)
    session.travel(room, "speedwalk", name)
    others = "".join(f"\n  also #{i} {n} ({d} steps)" for i, n, d in matches[1:4])
    note(f"walking {len(route)} steps to #{room} {name}{others}")


async def _look_then_go(session, text: str, note) -> None:
    """Look, and if that puts the map right, walk after all."""
    from .outbound import HIGH
    from .patrol import LOOK, LOOK_TIMEOUT

    mapper = session.mapper
    session.queue.put(LOOK, HIGH)
    await session.bus.wait(events.ROOM, LOOK_TIMEOUT)
    if mapper.here is None:
        note("still lost -- walk a room or two, or /bind <where you are>")
        return
    _go(session, text, note)


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


def _ansivars(session, rest: str, note) -> None:
    """Read the character's own colour settings, or put them back.

    For somebody trying this client who goes back to the one they had: the
    markers stay on their character, and the colours they chose for those
    lines are gone.  Putting them back shows first, like /prefixes -- these
    are commands going to somebody's character.
    """
    from .ansivars import shown, touched

    kept = getattr(session, "ansivars", None)
    if kept is None:
        note("there is no character here to read settings from")
        return
    words = rest.lower().split()

    if not words:
        if getattr(session, "_writer", None) is None:
            note("not connected")
            return
        note("asking 3K for its ansivars page -- the pager is answered for you")
        session.ask_ansivars()
        return

    if words[0] in ("show", "list"):
        if not kept.saved:
            note("nothing saved yet -- /ansivars reads them")
            return
        snap = kept.saved[-1]
        note(f"saved {snap['when']}:\n" + "\n".join(
            f"  {name:<14} {shown(v['pref']) or '-':<14} {shown(v['suff']) or '-'}"
            for name, v in sorted(snap["vars"].items())))
        return

    if words[0] not in ("restore", "back"):
        note("/ansivars, /ansivars show, /ansivars restore")
        return
    snap = kept.own(session.markers())
    if snap is None:
        note("nothing saved from before this client's markers went on -- "
             "/ansivars reads them" + (", but every reading so far already has "
                                       "the markers in it" if kept.saved else ""))
        return
    commands = kept.restore(snap, touched(session.prefixes), session.prefixes.verb)
    if not commands:
        note(f"the reading from {snap['when']} has none of the settings this "
             "client changes")
        return
    if words[1:2] not in (["go"], ["send"], ["set"]):
        note(f"from the reading on {snap['when']} -- only what this client "
             "changes, nothing else:\n"
             + "\n".join(f"  {shown(c)}" for c in commands)
             + "\n\nthe map reads rooms less well without the markers; "
               "/ansivars restore go to send them.")
        return
    for command in commands:
        session.queue.put(command)
    note(f"sent {len(commands)} settings; watch for the confirmations")


#: The speedruns' kinds, in the order they are listed, and what each is called.
SPEEDRUN_KINDS = [("area", "Areas"), ("mob", "Mobs"), ("crafting", "Crafting"),
                  ("shop", "Shops"), ("eq", "Equipment"), ("clan", "Clan halls"),
                  ("item", "Items"), ("misc", "Other")]
#: What somebody might type for a kind.
SPEEDRUN_WORDS = {"area": "area", "areas": "area", "mob": "mob", "mobs": "mob",
                  "crafting": "crafting", "craft": "crafting", "shop": "shop",
                  "shops": "shop", "eq": "eq", "equipment": "eq", "gear": "eq",
                  "clan": "clan", "clans": "clan", "hall": "clan", "halls": "clan",
                  "item": "item", "items": "item", "misc": "misc", "other": "misc"}


def _speedruns(session, rest: str, note) -> None:
    """Where you can go by name, and how far each is from here.

    The speedruns imported from 3kdb are the names /go knows.  Listing them
    was /marks, which stopped at forty and said nothing about distance or
    whether a place could be reached at all.  A few cannot; walking in once
    teaches the map the way.  (A quarter used to, until the importer stopped
    throwing away tt++'s unnamed rooms and walking through its void spacers --
    see tintin.import_map.)
    """
    store = getattr(session, "store", None)
    mapper = getattr(session, "mapper", None)
    if store is None:
        note("mapping is off (--no-map)")
        return
    marks = store.landmarks("", limit=100000)
    if not marks:
        note("no speedruns in the map -- Options -> Updates takes them from 3kdb")
        return
    lost = mapper is None or mapper.here is None
    steps = {} if lost else mapper.reach({int(m["room_id"]) for m in marks})
    label = dict(SPEEDRUN_KINDS)

    def row(m) -> str:
        n = steps.get(int(m["room_id"]))
        far = "" if lost else ("can't reach" if n is None
                               else "here" if n == 0 else f"{n} steps")
        return f"  {m['name']:<16} {far:>11}  {(m['note'] or '')[:52]}"

    def order(ms):
        return sorted(ms, key=lambda m: (steps.get(int(m["room_id"])) is None,
                                         steps.get(int(m["room_id"]), 0),
                                         m["name"]))

    head = ("the map does not know where you are, so no distances -- walk a "
            "room first.\n" if lost else "")
    q = rest.strip().lower()
    if not q:
        out = [head + f"{len(marks)} places /go knows by name, nearest first:"]
        for kind, title in SPEEDRUN_KINDS:
            some = [m for m in marks if (m["kind"] or "misc") == kind]
            if not some:
                continue
            can = sum(1 for m in some if int(m["room_id"]) in steps)
            out.append(f"\n  {title} -- {len(some)}"
                       + ("" if lost else f", {can} you can reach"))
            out += [row(m) for m in order(some)[:5]]
        out.append("\n/speedruns <word> for the rest: a kind (areas, mobs, "
                   "shops, crafting...) or part of a name.  /go <name> walks there.")
        note("\n".join(out))
        return

    kind = SPEEDRUN_WORDS.get(q)
    if kind:
        hits = [m for m in marks if (m["kind"] or "misc") == kind]
        title = label[kind]
    else:
        words = q.split()
        hits = [m for m in marks if all(
            w in f"{m['name']} {m['note'] or ''} {m['kind'] or ''}".lower()
            for w in words)]
        title = f"matching {rest.strip()!r}"
    if not hits:
        note(f"no speedruns {title} -- /speedruns on its own lists them all")
        return
    hits = order(hits)
    shown = hits[:60]
    out = [head + f"{title}: {len(hits)}"] + [row(m) for m in shown]
    if len(hits) > len(shown):
        out.append(f"  ...and {len(hits) - len(shown)} more -- add a word to narrow it")
    if not lost and any(int(m["room_id"]) not in steps for m in shown):
        out.append("\ncan't reach: the map has no way in from here yet.  Walk in once "
                   "and it learns the way.")
    out.append("/go <name> walks there.")
    note("\n".join(out))
