"""Bringing zMUD settings across: its exported settings file.

zMUD keeps its settings in a binary .mud file, but exports them as text, one
command to a line:

    #TRIGGER {pattern} {commands} "class|subclass" {disable}
    #TRIGGER "id" {pattern} {commands} "class"
    #ALIAS name {commands} "class"
    #PATH name {3n2el;enter portal}
    #CLASS {class|subclass}          (declarations, then #CLASS 0)

This reads that into the same preview as a TinTin++ file (ttimport.Found),
so Options -> From TinTin++ / zMUD shows both the same way.

zMUD, not tt++, in the details that matter:

* Patterns: `*` anything, `?` one character, `%w` letters, `%a` letters and
  digits, `%d` digits, `%n` a signed number, `%s` spaces, `%x` non-spaces,
  `%p` punctuation, `(...)` a capture, `{a|b}` either, `~` the next
  character as itself.  A pattern matches anywhere in a line.
* Capitals: zMUD has a Case sensitive option; not one trigger in a real
  export had it on, so an imported trigger ignores capitals unless {case}.
* Commands: `%1` is {1}, `%-1` everything typed ({args}); `#WAIT 3000` is a
  wait of three seconds -- zMUD's holds back what follows, as ours does;
  `#T- name` / `#T+ name` switch a class off and on, which is `/group`.
* Speedwalks: `.3n2e` is n n n e e, and `(climb pipe)` a step in brackets.
  The diagonals are letters of their own, h j k l, and which is which was
  worked out from the map rather than remembered: every one of a real
  export's paths walks cleanly only with h=nw, j=ne, k=sw, l=se, and its
  169-step Section Z walk then fits exactly one room in the world -- the
  Section Z entrance.
* A #PATH becomes a route, and when its moves fit exactly one room on the
  map, that room is its start.
"""

from __future__ import annotations

import re

from .ttimport import GROUP, MIN_EVERY, Found

#: zMUD's speedwalk letters.  See the module notes for how the diagonals
#: were established.
DIRECTIONS = {"n": "n", "s": "s", "e": "e", "w": "w", "u": "u", "d": "d",
              "h": "nw", "j": "ne", "k": "sw", "l": "se"}
WALK = re.compile(r"(\d*)([nsewudhjkl]|\([^()]*\))")

#: zMUD pattern wildcards, as its help lists them.
WILD = {"d": r"\d+", "n": r"[+-]?\d+", "w": r"[A-Za-z]+", "a": r"[A-Za-z0-9]+",
        "s": r"\s+", "x": r"\S+", "p": r"[^\w\s]+", "*": r".*"}

#: zMUD's commands for walking a path a step at a time.  The client's routes
#: do that instead, so a rule driving one does not come across.
SLOW = {"step", "pause", "slow", "stop", "ok", "resume", "path", "pa"}


class _Unsupported(Exception):
    pass


# --- reading a line ---------------------------------------------------------------

def is_zmud(text: str) -> bool:
    """Does this look like a zMUD export rather than a tt++ file?"""
    return bool(re.search(r"(?mi)^#(trigger|tr|path|alarm|key)\b|^#class 0\s*$", text))


def _args(text: str) -> list[tuple[str, str]]:
    """A zMUD line's arguments: ('{', braced), ('"', quoted) or ('', word)."""
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "{":
            depth, j = 0, i
            while j < len(text):
                if text[j] == "~":
                    j += 2
                    continue
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= len(text):
                raise _Unsupported("braces that do not close")
            out.append(("{", text[i + 1:j]))
            i = j + 1
        elif c == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise _Unsupported("a quote that does not close")
            out.append(('"', text[i + 1:j]))
            i = j + 1
        else:
            j = i
            while j < len(text) and not text[j].isspace():
                j += 1
            out.append(("", text[i:j]))
            i = j
    return out


def _split(body: str) -> list[str]:
    """Commands in a body: `;` outside braces, `~;` kept."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c == "~" and i + 1 < len(body):
            buf.append(body[i:i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c == ";" and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    out.append("".join(buf).strip())
    return [p for p in out if p]


# --- patterns ------------------------------------------------------------------------

def translate(pattern: str, case: bool = False) -> tuple[str | None, str]:
    """A zMUD pattern as a Python regex, and why not if it cannot be."""
    out, i, s = [], 0, pattern.rstrip()
    while i < len(s):
        c = s[i]
        if c == "~" and i + 1 < len(s):
            out.append(re.escape(s[i + 1]))
            i += 2
        elif c == "*":
            out.append(".*")
            i += 1
        elif c == "?":
            out.append(".")
            i += 1
        elif c == "^" and i == 0 or c == "$" and i == len(s) - 1:
            out.append(c)
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == "[":
            j = s.find("]", i)
            if j < 0:
                return None, "a [ that does not close"
            out.append("[" + s[i + 1:j].replace("\\", "\\\\") + "]*")
            i = j + 1
        elif c == "{":
            j = s.find("}", i)
            if j < 0:
                return None, "a { that does not close"
            inner = s[i + 1:j]
            if inner.startswith("^"):
                return None, "{^...}, zMUD's 'not this'"
            out.append("(" + "|".join(re.escape(x) for x in inner.split("|")) + ")")
            i = j + 1
        elif c == "%" and i + 1 < len(s):
            num = re.match(r"\d{1,2}", s[i + 1:])
            if num:
                out.append("(.*?)")
                i += 1 + len(num.group(0))
            elif s[i + 1] in WILD:
                out.append(WILD[s[i + 1]])
                i += 2
            else:
                word = re.match(r"%\w+", s[i:]).group(0) if re.match(r"%\w", s[i:]) else s[i:i + 2]
                return None, f"{word} in a pattern"
        elif c in "&@":
            return None, f"{c}, which zMUD fills from a variable"
        else:
            out.append(c if c == " " else re.escape(c))
            i += 1
    regex = ("" if case else "(?i)") + "".join(out)
    try:
        re.compile(regex)
    except re.error as exc:
        return None, f"a pattern Python's regex cannot read ({exc})"
    return regex, ""


# --- commands --------------------------------------------------------------------------

def speedwalk(piece: str) -> list[str] | None:
    """`.3n2e(climb pipe)` as its steps; None if it is not a speedwalk."""
    if not piece.startswith(".") or len(piece) < 2:
        return None
    body = piece[1:]
    if WALK.sub("", body).strip():
        return None
    steps: list[str] = []
    for count, step in WALK.findall(body):
        step = step[1:-1].strip() if step.startswith("(") else DIRECTIONS[step]
        steps += [step] * min(int(count or 1), 99)
    return steps


def changed_vars(text: str) -> set[str]:
    """Variables a command list sets as it runs: #VAR, #VA, #ADD, #AD, #MATH."""
    return {m.group(1).lower() for m in re.finditer(
        r"#(?:variable|var|va|add|ad|math)\s+\{?@?(\w+)", text, re.I)}


class Context:
    def __init__(self, vars_, aliases, classes, ids=()):
        self.vars_ = vars_
        self.aliases = aliases          # lower-cased name -> body
        self.classes = classes          # every class path
        self.ids = {i.lower() for i in ids}   # triggers named "like this"
        self.depth = 0


def group_of(path: str) -> str:
    """zMUD's `areas|zombies` as a group name: `areas/zombies`."""
    return path.replace("|", "/") if path else ""


def _toggle(name: str, on: bool, ctx: Context) -> list[dict]:
    """#T+ / #T- a class: `/group` for it, and every class inside it, as
    zMUD switches a class and all it holds."""
    want = name.strip().strip("{}\"").lower()
    hits = [c for c in ctx.classes
            if c.lower() == want or c.lower().endswith("|" + want)]
    sign = "+" if on else "-"
    if want in ctx.ids and not hits:
        raise _Unsupported(f"#T{sign} {name.strip()}, which switches one trigger by "
                           "its id -- give that trigger a group of its own instead")
    if len({h.lower() for h in hits}) != 1:
        raise _Unsupported(f"#T{sign} {name.strip()}, which names no one class")
    root = hits[0]
    under = [c for c in ctx.classes if c == root or c.startswith(root + "|")]
    return [{"type": "send", "text": f"/group {group_of(c)} {'on' if on else 'off'}"}
            for c in under]


def _fill(text: str, ctx: Context, alias: bool) -> str:
    if re.search(r"%[a-z]\w*\(", text, re.I):
        raise _Unsupported(re.search(r"%[a-z]\w*", text, re.I).group(0) + "(), a scripting function")

    def var(m):
        name = m.group(1)
        if name.lower() in ctx.vars_:
            return ctx.vars_[name.lower()]
        raise _Unsupported(f"@{name}, which is set as it runs")
    text = re.sub(r"@(\w+)", var, text)
    text = text.replace("%-1", "{args}")
    if re.search(r"%-\d", text):
        raise _Unsupported("%-2 and the like")
    text = re.sub(r"%(\d{1,2})", r"{\1}", text)
    return re.sub(r"~(.)", r"\1", text)


def body(text: str, ctx: Context, alias: bool, notes: list[str], flags: dict) -> list[dict]:
    """A zMUD command list as the client's actions, or _Unsupported."""
    acts: list[dict] = []
    for piece in _split(text):
        walk = speedwalk(piece)
        if walk is not None:
            acts += [{"type": "send", "text": s} for s in walk]
            notes.append("a speedwalk, as its steps")
            continue
        m = (re.match(r"#(\d+)\s*(\S.*)\Z", piece, re.S)            # #4N, #3 get all
             or re.match(r"#(\w+|[+-])\s*(.*)\Z", piece, re.S))
        if not m:
            word, _, rest = piece.partition(" ")
            if word.lower() in ctx.aliases and ctx.depth < 6:
                inner = ctx.aliases[word.lower()]
                used = re.search(r"%-?\d", inner)
                if used:
                    words = rest.split()
                    inner = inner.replace("%-1", rest)
                    inner = re.sub(r"%(\d{1,2})", lambda x: words[int(x.group(1)) - 1]
                                   if int(x.group(1)) <= len(words) else "", inner)
                elif rest:
                    inner += " " + rest
                notes.append(f"uses your alias {word}, put in its place")
                ctx.depth += 1
                try:
                    acts += body(inner, ctx, alias, notes, flags)
                finally:
                    ctx.depth -= 1
                continue
            acts.append({"type": "send", "text": _fill(piece, ctx, alias)})
            continue
        cmd, arg = m.group(1).lower(), m.group(2).strip()
        if cmd.isdigit():
            inner = body(arg.strip("{}"), ctx, alias, notes, flags)
            acts += inner * min(int(cmd), 99)
        elif cmd in ("wait", "wa"):
            ms = arg.strip("{} ") or "1000"
            if not ms.isdigit():
                raise _Unsupported("#WAIT for a variable time")
            acts.append({"type": "wait", "text": f"{int(ms) / 1000:g}"})
        elif cmd in ("t+", "t-") or cmd == "t" and arg[:1] in "+-":
            on = (cmd == "t+") or (cmd == "t" and arg.startswith("+"))
            name = arg[1:] if cmd == "t" else arg
            acts += _toggle(name, on, ctx)
        elif cmd == "gag" and not arg:
            flags["gag"] = True
        elif cmd in ("cap", "capture"):
            notes.append("#CAP dropped: there is no capture window "
                         "(tells and channels have the messages window)")
        elif cmd in ("beep", "noop", "no"):
            if cmd == "beep":
                notes.append("#BEEP dropped: choose sounds under Options -> Sounds")
        elif cmd in ("echo", "show", "sh") and arg:
            acts.append({"type": "log", "text": _fill(arg.strip("{}"), ctx, alias)})
        elif cmd == "cr":
            acts.append({"type": "send", "text": ""})
        elif cmd in SLOW:
            raise _Unsupported(f"#{cmd.upper()}, zMUD's slow walking (routes do that here)")
        else:
            raise _Unsupported(f"#{cmd.upper()}")
    while acts and acts[-1]["type"] == "wait" and ctx.depth == 0:
        # zMUD lets a #WAIT end the list, where it does nothing at all; a
        # rule here is refused for one, so the preview and Import disagreed.
        acts.pop()
        notes.append("a #WAIT with nothing after it, dropped: it did nothing")
    return acts


# --- a whole file --------------------------------------------------------------------------

def read(files: list[tuple[str, str]], rooms=None) -> list[Found]:
    """Every line of every export, as what it becomes.

    `rooms`, if given, finds a path's start: a function taking the steps and
    returning the rooms they can be walked from.
    """
    lines: list[tuple[str, int, str]] = []
    for fname, text in files:
        for n, ln in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
            if ln.strip():
                lines.append((fname, n, ln.rstrip()))
    classes: list[str] = []
    vars_: dict[str, str] = {}
    changed: set[str] = set()
    aliases: dict[str, str] = {}
    for _f, _n, ln in lines:
        head = re.match(r"#(\w+)\s*(.*)\Z", ln)
        if not head:
            continue
        cmd, rest = head.group(1).lower(), head.group(2)
        try:
            args = _args(rest)
        except _Unsupported:
            continue
        if cmd in ("class", "cl") and args and args[0][1] != "0":
            classes.append(args[0][1])
        elif cmd in ("var", "variable") and len(args) >= 2 and args[1][0] == "{":
            vars_[args[0][1].lstrip("'").lower()] = args[1][1]
        elif cmd in ("alias", "al") and len(args) >= 2:
            aliases[args[0][1].lower()] = args[1][1]
        changed |= changed_vars(rest)
    for name in changed:
        vars_.pop(name, None)
    ids = [m.group(1) for _f, _n, ln in lines
           for m in [re.match(r'#(?:trigger|tr)\s+"([^"]+)"', ln, re.I)] if m]
    ctx = Context(vars_, aliases, classes, ids)

    found: list[Found] = []
    for fname, n, ln in lines:
        where, first = f"{fname}:{n}", ln[:120]
        head = re.match(r"#(\w+)\s*(.*)\Z", ln)
        if not head:
            continue
        cmd, rest = head.group(1).lower(), head.group(2)
        if cmd in ("class", "cl", "var", "variable"):
            continue
        try:
            args = _args(rest)
        except _Unsupported as why:
            found.append(Found("skip", where, first, why=f"{why} -- not read"))
            continue
        item = _one(cmd, args, ctx, where, first, rooms)
        if item is not None:
            found.append(item)
    return found


def _tail(args, start: int) -> tuple[str, set[str]]:
    """The class and the options after a rule's own arguments."""
    klass, opts = "", set()
    for kind, value in args[start:]:
        if kind == '"':
            klass = value
        elif kind == "{":
            opts |= {o.strip().lower() for o in value.split("|")}
    return klass, opts


def _one(cmd, args, ctx, where, first, rooms) -> Found | None:
    notes: list[str] = []
    flags: dict = {}
    kind = {"trigger": "trigger", "tr": "trigger", "action": "trigger", "ac": "trigger",
            "alias": "alias", "al": "alias", "path": "route", "pa": "route",
            "alarm": "timer", "key": "key"}.get(cmd)
    if kind is None:
        return None
    try:
        if kind == "key":
            return Found("skip", where, first, why="#KEY: set keys under Options -> Keyboard")
        if kind == "trigger":
            if args and args[0][0] == '"':
                args = args[1:]                          # its id
            if len(args) < 2:
                raise _Unsupported("a #TRIGGER without its commands")
            klass, opts = _tail(args, 2)
            regex, why = translate(args[0][1], case="case" in opts)
            if regex is None:
                raise _Unsupported(why)
            return trigger_found(regex, args[1][1], klass, "disable" not in opts,
                                 ctx, where, first)
        if kind == "alias":
            if len(args) < 2:
                raise _Unsupported("an #ALIAS without its commands")
            klass, opts = _tail(args, 2)
            return alias_found(args[0][1], args[1][1], klass, "disable" not in opts,
                               ctx, where, first)
        if kind == "timer":
            if len(args) < 2:
                raise _Unsupported("an #ALARM without its commands")
            klass, opts = _tail(args, 2)
            return alarm_found(args[0][1], args[1][1], klass, "disable" not in opts,
                               ctx, where, first)
        if kind == "route":
            if len(args) < 2:
                raise _Unsupported("a #PATH without its steps")
            return _route(args[0][1], args[1][1], ctx, where, first, rooms)
    except _Unsupported as why:
        return Found("skip", where, first, why=f"{kind} uses {why}")
    return None


def trigger_found(regex: str, text: str, klass: str, enabled: bool, ctx: Context,
                  where: str, first: str) -> Found:
    """A trigger from its translated pattern and its commands (zMUD or CMUD)."""
    notes: list[str] = []
    flags: dict = {}
    try:
        acts = body(text, ctx, False, notes, flags)
        if not acts and not flags.get("gag"):
            if any(n.startswith("#CAP") for n in notes):
                raise _Unsupported("only #CAP, which copies the line to a capture "
                                   "window -- tells and channels have the messages window")
            raise _Unsupported("nothing in it this can send")
    except _Unsupported as why:
        return Found("skip", where, first, why=f"trigger uses {why}")
    rule = {"kind": "trigger", "mode": "regex", "pattern": regex, "actions": acts,
            "gag": bool(flags.get("gag")), "enabled": enabled,
            "group": group_of(klass) or GROUP}
    return Found("gag" if flags.get("gag") and not acts else "trigger",
                 where, first, rule, notes=_once(notes))


def alias_found(word: str, text: str, klass: str, enabled: bool, ctx: Context,
                where: str, first: str, append: bool | str = True) -> Found:
    """An alias.  `append`: what was typed after it goes on the end, unless it
    uses %1 and the like.  zMUD always does, onto the last command.  CMUD
    says per alias, and `append="every"` is its way: onto every command,
    until one uses an argument -- its author on the difference: "zMUD only
    appended to the last command; CMUD keeps track of the last parameter
    referenced so far"."""
    notes: list[str] = []
    try:
        if not re.fullmatch(r"[^\s{}()]+", word):
            raise _Unsupported("a name that is a pattern")
        acts = body(text, ctx, True, notes, {})
        if not acts:
            raise _Unsupported("nothing in it this can send")
    except _Unsupported as why:
        return Found("skip", where, first, why=f"alias uses {why}")
    if append == "every":
        for n, a in enumerate(acts):
            if re.search(r"\{(args|\d{1,2})\}", a["text"]):
                break                             # an argument used: no more
            if a["type"] == "send":
                acts[n] = {"type": "send", "text": a["text"] + " {args}"}
    elif (append and not re.search(r"%-?\d", text) and acts[-1]["type"] == "send"
            and not _split(text)[-1].startswith(("#", "."))):
        acts[-1] = {"type": "send", "text": acts[-1]["text"] + " {args}"}
    rule = {"kind": "alias", "mode": "command", "pattern": word, "name": word,
            "actions": acts, "enabled": enabled, "group": group_of(klass) or GROUP}
    return Found("alias", where, first, rule, notes=_once(notes))


def alarm_found(when: str, text: str, klass: str, enabled: bool, ctx: Context,
                where: str, first: str) -> Found:
    """An alarm that goes off every so often -- `*5:00`, every five minutes --
    as a timer.  One tied to the clock (`*:*5:00`) is not."""
    notes: list[str] = []
    try:
        m = re.fullmatch(r"\*(?:(\d+):)?(\d+)", when.strip())
        if not m:
            raise _Unsupported(f"an alarm at {when} rather than every so often")
        every = int(m.group(1) or 0) * 60 + int(m.group(2))
        if every < MIN_EVERY:
            raise _Unsupported(f"every {every}s is faster than the game's beat")
        acts = body(text, ctx, False, notes, {})
        if not acts:
            raise _Unsupported("nothing in it this can send")
    except _Unsupported as why:
        return Found("skip", where, first, why=f"timer uses {why}")
    rule = {"kind": "timer", "name": f"alarm {when}", "every": float(every),
            "actions": acts, "enabled": enabled, "group": group_of(klass) or GROUP}
    return Found("timer", where, first, rule, notes=_once(notes))


def _once(notes: list[str]) -> list[str]:
    return list(dict.fromkeys(notes))


def _route(name: str, text: str, ctx: Context, where: str, first: str, rooms) -> Found:
    """A #PATH as a route: its moves, and the ordinary commands among them.

    zMUD paths often end with housekeeping -- `#T- zombies`, `#BEEP`, an alias
    -- which a route cannot run; that is dropped, and said so.
    """
    steps: list[str] = []
    notes: list[str] = []
    for piece in _split(text):
        walk = speedwalk(piece if piece.startswith(".") else "." + piece)
        if walk is not None:
            steps += walk
            continue
        if piece.startswith("#") or piece.split()[0].lower() in ctx.aliases:
            notes.append(f"{piece.split()[0]} dropped: a route only walks and sends")
            continue
        steps.append(_fill(piece, ctx, False))
    if not steps:
        return Found("skip", where, first, why="route uses nothing it can walk")
    rule = {"name": name, "path": ", ".join(steps), "start": 0}
    if rooms is not None:
        moves = []
        for s in steps:
            if s not in DIRECTIONS.values():
                break
            moves.append(s)
        if len(moves) >= 8:
            fits = rooms(moves)
            if len(fits) == 1:
                rule["start"] = fits[0]
                notes.append(f"starts at room {fits[0]}: its moves fit nowhere else")
    return Found("route", where, first, rule, notes=_once(notes))
