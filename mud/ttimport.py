"""Bringing TinTin++ settings across: aliases.tin, actions.tin and the rest.

A player arriving from tt++ has years of #alias, #action, #gag and #ticker in
files.  This reads those files and says, for each one, what it becomes here --
an alias, a trigger, a gag, a timer -- or why it does not come across.  Nothing
is imported until the player has seen that and pressed Import.

What translates:

    #alias {gk} {kill %1;glance}        an alias; %1 -> {1}, %0 -> {args}
    #action {pattern} {cmds} {pri}      a trigger, the pattern translated
    #gag {text}                         a gag
    #ticker {name} {cmds} {secs}        a timer
    #class {name} {open} ... {close}    a group, for everything in between
    #delay 2 {cmd}, last in a body      a wait, then the command
    #if {!$idle_flag} {cmds}            just the commands: 3kdb's idle check is
                                        what the deadman already does
    $var, set by #var in these files    its value, filled in now
    #10 cmd                             the command ten times

and a tt++ alias that uses no %-argument has what you typed after it added to
its last command, as tt++ does.

What does not: real tt++ programming -- #if on anything else, #math, #list,
#foreach, #regexp, #format, #var set as it runs -- and #highlight and
#substitute, which the client has no equivalent of.  Each is named with its
reason, so the player can write it as a script instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: tt++ commands may be shortened to any unambiguous start: #act, #ali, #VAR.
KNOWN = ("action", "alias", "class", "delay", "echo", "gag", "highlight",
         "macro", "nop", "read", "send", "showme", "substitute", "ticker",
         "ungag", "unaction", "unalias", "unticker", "variable", "var",
         "if", "elseif", "else", "math", "list", "foreach", "regexp", "format",
         "case", "switch", "default", "loop", "while", "break", "return",
         "unvar", "unvariable", "local", "script", "map", "path", "cr",
         "bell", "config", "session", "zap", "event", "function", "line",
         "prompt", "split", "tab", "button", "pathdir", "replace", "system",
         "write", "log", "cursor", "info", "kill", "all", "port", "sub")

#: 3kdb's own class names, the same in every character folder: as groups
#: they would say nothing.  Rules in them go in the importer's own group.
PLAIN_CLASSES = {"player_aliases", "player_actions", "player_tickers", "global"}
GROUP = "tintin"
#: The shortest timer the client keeps (rules.MIN_EVERY).
MIN_EVERY = 2.0


def command_name(word: str) -> str:
    """#ACT -> action, #ali -> alias, #var -> variable."""
    w = word.lower()
    if w in ("var", "act", "ali", "sub", "tick"):
        return {"var": "variable", "act": "action", "ali": "alias",
                "sub": "substitute", "tick": "ticker"}[w]
    if w in KNOWN:
        return "variable" if w == "var" else w
    for name in KNOWN:
        if name.startswith(w) and len(w) >= 3:
            return name
    return w


# --- reading tt++ ----------------------------------------------------------------

def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def split_commands(text: str) -> list[str]:
    """Commands at this level: `;` or a line break outside braces ends one."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            buf.append(text[i:i + 2])
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ";\n" and not (ch == "\n" and _continues(text, i)):
            piece = "".join(buf).strip()
            if piece:
                out.append(piece)
            buf = []
        else:
            buf.append(ch)
        i += 1
    piece = "".join(buf).strip()
    if piece:
        out.append(piece)
    return out


def _continues(text: str, at: int) -> bool:
    """Does the command go on past the line break at `at`?

    tt++ lets an argument start on the next line:

        #act {Use your Auras Now!}
        {strengthen Friend}

    so a line whose first thing is `{` belongs to the command above.
    """
    j = at + 1
    while j < len(text) and text[j] in " \t\r\n":
        j += 1
    return j < len(text) and text[j] == "{"


def split_args(text: str) -> list[str]:
    """`{a b} c {d}` -> ['a b', 'c', 'd']: braced, or a bare word."""
    args, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        if text[i] == "{":
            depth, j = 0, i
            while j < len(text):
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            args.append(text[i + 1:j].strip())
            i = j + 1
        else:
            j = i
            while j < len(text) and not text[j].isspace():
                j += 1
            args.append(text[i:j])
            i = j
    return args


def parse_command(text: str) -> tuple[str | None, list[str]]:
    """(name, args) for a #command; (None, [text]) for anything else."""
    m = re.match(r"#(\w+)\s*(.*)\Z", text, re.S)
    if not m:
        return None, [text]
    word = m.group(1)
    if word.isdigit():
        return "repeat", [word, m.group(2).strip()]
    return command_name(word), split_args(m.group(2))


# --- patterns ----------------------------------------------------------------------

SIMPLE = {"*": ".*", "+": ".+", "?": ".?", ".": ".", "w": r"\w+", "W": r"\W+",
          "d": r"\d+", "D": r"\D+", "s": r"\s+", "S": r"\S+", "a": r"[\s\S]*",
          "A": r"\n", "p": r"[\x20-\x7e]", "P": r"[^\x20-\x7e]", "u": r".",
          "U": r"[\x00-\x7f]"}


def translate(pattern: str) -> tuple[str | None, str]:
    """A tt++ pattern as a Python regex, and why not if it cannot be.

    Captures come out in the order they appear, as tt++ numbers them: a
    `%1`, a `( )` or a `{ }` each takes the next number, so `%1` in the
    commands is `{1}` here.
    """
    out: list[str] = []
    s = pattern
    i, end = 0, len(s)
    anchored_end = s.endswith("$") and not s.endswith("\\$")
    if anchored_end:
        end -= 1
    if s.startswith("%i") or s.startswith("%I"):
        out.append("(?i)")                # ignore capitals, for all of it
        i = 2
    if s.startswith("^", i):
        out.append("^")
        i += 1
    if re.search(r"(?<!%)%[iI]", s[i:]):
        return None, "%i (ignore capitals) part way through a pattern"
    while i < end:
        c = s[i]
        if c == "\\" and i + 1 < end:
            out.append(re.escape(s[i + 1]))
            i += 2
            continue
        if c == "{":
            depth, j = 0, i
            while j < end:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= end:
                return None, "an unclosed {"
            out.append("(" + s[i + 1:j] + ")")
            i = j + 1
            continue
        if c == "(":
            out.append("(")
            i += 1
            continue
        if c == ")":
            out.append(")")
            i += 1
            continue
        if c == "%" and i + 1 < end:
            code = s[i + 1]
            num = re.match(r"\d{1,2}", s[i + 1:])
            if num:
                out.append("(.*?)")
                i += 1 + len(num.group(0))
                continue
            if code in SIMPLE:
                out.append(SIMPLE[code])
                i += 2
                continue
            if code == "%":
                out.append("%")
                i += 2
                continue
            return None, f"%{code} in a pattern"
        out.append(c if c == " " else re.escape(c))   # spaces read as spaces
        i += 1
    if anchored_end:
        out.append("$")
    regex = "".join(out)
    try:
        re.compile(regex)
    except re.error as exc:
        return None, f"a pattern Python's regex cannot read ({exc})"
    return regex, ""


def plain_text(pattern: str) -> bool:
    """Nothing in it that means anything to tt++: a `contains` will do."""
    return not re.search(r"[%{}()\\^$]", pattern)


# --- commands ------------------------------------------------------------------------

@dataclass
class Found:
    """One thing read: what it becomes, or why it does not."""
    kind: str                     # trigger | alias | gag | timer | skip
    source: str                   # "actions.tin:12"
    text: str                     # the tt++ as written, first line
    rule: dict | None = None
    why: str = ""
    notes: list[str] = field(default_factory=list)


class _Unsupported(Exception):
    pass


def threekdb_names() -> set[str]:
    """The aliases 3kdb itself defines (tt3kdb.txt), lower-cased."""
    from importlib import resources
    try:
        text = (resources.files(__package__ or "mud") / "tt3kdb.txt").read_text()
    except OSError:
        return set()
    return {ln.strip().lower() for ln in text.splitlines()
            if ln.strip() and not ln.startswith("#")}


@dataclass
class _Context:
    vars_: dict[str, str]
    #: the player's own command-style aliases, by lower-cased name: their body
    aliases: dict[str, str]
    threekdb: set[str]
    depth: int = 0


def _var(value: str, vars_: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name in vars_:
            return vars_[name]
        raise _Unsupported(f"${name}, which is set as it runs")
    return re.sub(r"\$\{(\w+)\}|\$(\w+)(?!\[)", sub, value)


def _args_to_rule(text: str, alias: bool) -> str:
    text = text.replace("%0", "{args}" if alias else "{0}")
    return re.sub(r"%(\d{1,2})", r"{\1}", text)


def _call(piece: str, ctx: _Context, alias: bool, notes: list[str]) -> list[dict] | None:
    """A command that is really an alias: the player's own is put in its
    place; 3kdb's own machinery cannot come across.  None for a plain
    command."""
    word, _, rest = piece.partition(" ")
    key = word.lower()
    if key in ctx.aliases and ctx.depth < 6:
        body = ctx.aliases[key]
        words = rest.split()
        # tt++'s own rule: %0 is all of it, %1 the first word, and an alias
        # that uses none has it put on the end.
        if re.search(r"%\d", body):
            body = body.replace("%0", rest)
            body = re.sub(r"%(\d{1,2})", lambda m: words[int(m.group(1)) - 1]
                          if int(m.group(1)) <= len(words) else "", body)
        elif rest:
            body = body.rstrip().rstrip(";") + " " + rest
        notes.append(f"uses your alias {word}, put in its place")
        inner = _Context(ctx.vars_, ctx.aliases, ctx.threekdb, ctx.depth + 1)
        return translate_body(body, inner, alias, notes)
    if word.startswith(".") or (key in ctx.threekdb and re.search(r"[+\-_]$|^\.", word)):
        raise _Unsupported(f"3kdb's own {word}, which is part of 3kdb rather than 3K")
    if key in ctx.threekdb and ctx.depth == 0:
        notes.append(f"{word} is also a 3kdb command: if you meant 3kdb's, it is not here")
    return None


def translate_body(body: str, ctx: _Context, alias: bool,
                   notes: list[str]) -> list[dict]:
    """A tt++ command list as the client's actions, or _Unsupported."""
    vars_ = ctx.vars_
    actions: list[dict] = []
    pieces = split_commands(body)
    for n, piece in enumerate(pieces):
        name, args = parse_command(piece)
        last = n == len(pieces) - 1
        if name is None:
            if "@" in piece and re.search(r"@\w+\{", piece):
                raise _Unsupported("a tt++ @function")
            if re.search(r"\$\w+\[", piece):
                raise _Unsupported("a $variable[with a key]")
            text = _var(piece, vars_)
            expanded = _call(text, ctx, alias, notes)
            if expanded is not None:
                actions.extend(expanded)
                continue
            actions.append({"type": "send", "text": _args_to_rule(text, alias)})
        elif name == "nop":
            continue
        elif name == "repeat":
            times, rest = int(args[0]), args[1]
            if not 1 <= times <= 99 or not rest:
                raise _Unsupported(f"#{args[0]} with nothing to repeat")
            inner = translate_body(rest.strip("{}"), ctx, alias, notes)
            actions.extend(inner * times)
        elif name == "send" and args:
            actions.append({"type": "send", "text": _args_to_rule(_var(args[0], vars_), alias)})
        elif name in ("showme", "echo") and args:
            shown = re.sub(r"<[0-9a-fA-FgGx]{3}>|\\e\[[0-9;]*m", "", args[0])
            actions.append({"type": "log", "text": _args_to_rule(_var(shown, vars_), alias)})
        elif name == "delay" and len(args) >= 2:
            try:
                seconds = float(_var(args[0], vars_))
            except ValueError:
                raise _Unsupported("#delay with a named timer") from None
            if not last:
                raise _Unsupported("#delay with more after it (tt++ carries on "
                                   "at once; here a wait holds the rest back)")
            actions.append({"type": "wait", "text": f"{seconds:g}"})
            actions.extend(translate_body(args[1], ctx, alias, notes))
        elif name == "if" and len(args) >= 2 and _idle_check(args[0]):
            if len(args) >= 3 and split_commands(args[2]) not in ([], ["#nop"], ["#NOP"]):
                raise _Unsupported("#if {!$idle_flag} with an else")
            notes.append("#if {!$idle_flag} dropped: the deadman does that")
            actions.extend(translate_body(args[1], ctx, alias, notes))
        else:
            raise _Unsupported(f"#{name}")
    return actions


def _idle_check(cond: str) -> bool:
    return re.fullmatch(r"\s*\{?\s*!\s*\$idle_flag\s*\}?\s*", cond) is not None


# --- a whole file ----------------------------------------------------------------------

def read(files: list[tuple[str, str]], rooms=None) -> list[Found]:
    """Every file, in order, as what each thing in it becomes.

    A zMUD export is read by zmimport and a CMUD one by cmimport; `rooms`
    lets them find where one of their paths starts.
    """
    from . import cmimport, zmimport
    cm = [f for f in files if cmimport.is_cmud(f[1])]
    zm = [f for f in files if f not in cm and zmimport.is_zmud(f[1])]
    tt = [f for f in files if f not in cm and f not in zm]
    found = ((_read_tintin(tt) if tt else []) + (zmimport.read(zm, rooms) if zm else [])
             + (cmimport.read(cm, rooms) if cm else []))
    return [_checked(f) for f in found]


def _checked(f: Found) -> Found:
    """Held to the same check Import makes, so the preview never promises a
    rule that Import then refuses -- a CMUD #WA of an hour and more was."""
    if f.rule is None:
        return f
    if "path" in f.rule:
        from .botstore import Route
        fields = Route.__dataclass_fields__
        problem = Route(**{k: v for k, v in f.rule.items() if k in fields}).validate()
    else:
        from .rules import Rule
        fields = Rule.__dataclass_fields__
        problem = Rule(**{k: v for k, v in f.rule.items() if k in fields}).validate()
    if not problem:
        return f
    kind = {"gag": "gag", "timer": "timer", "alias": "alias", "route": "route"}.get(f.kind, "trigger")
    return Found("skip", f.source, f.text, why=f"{kind}: {problem}")


def _read_tintin(files: list[tuple[str, str]]) -> list[Found]:
    vars_: dict[str, str] = {}
    # Variables first, from every file: vars.tin is usually read before the
    # rest.  Only one that nothing changes as it runs is filled in -- your
    # aura list's `delay` is set to 2 and then counted up by #math, and
    # freezing it at 2 would be wrong -- so a name that any command body sets
    # is left out, and a rule that uses it is not imported.
    changed: set[str] = set()
    for _name, text in files:
        text = _strip_comments(text)
        for piece in split_commands(text):
            name, args = parse_command(piece)
            if name == "variable" and len(args) >= 2 and "{" not in args[1]:
                if args[0] in vars_ and vars_[args[0]] != args[1]:
                    changed.add(args[0])
                vars_.setdefault(args[0], args[1])
        for m in re.finditer(r"#(?:var|variable|math|format|list|regexp|local|unvar)"
                             r"\w*\s*\{?\s*(\w+)", text, re.I):
            if m.start() > 0 and text[:m.start()].count("{") > text[:m.start()].count("}"):
                changed.add(m.group(1))                    # inside a body
    for name in changed:
        vars_.pop(name, None)
    aliases: dict[str, str] = {}
    for _name, text in files:
        for piece in split_commands(_strip_comments(text)):
            name, args = parse_command(piece)
            if (name == "alias" and len(args) >= 2
                    and re.fullmatch(r"[^\s%{}()^$\\]+", args[0])):
                aliases[args[0].lower()] = args[1]
    ctx = _Context(vars_, aliases, threekdb_names())
    found: list[Found] = []
    for fname, text in files:
        group = ""
        text = _strip_comments(text)
        line_of = _line_index(text)
        for piece, at in _commands_with_lines(text, line_of):
            where = f"{fname}:{at}"
            first = piece.splitlines()[0][:120]
            name, args = parse_command(piece)
            if name is None:
                continue                # a bare command in the file: sent at load
            if name == "class" and len(args) >= 2:
                what = args[1].lower()
                if what == "open":
                    group = "" if args[0].lower() in PLAIN_CLASSES else args[0]
                elif what in ("close", "kill"):
                    group = "" if what == "close" else group
                continue
            if name in ("nop", "variable", "read", "unvar", "unvariable", "unalias",
                        "unaction", "unticker", "ungag"):
                continue
            item = _one(name, args, ctx, where, first)
            if item is None:
                continue
            if item.rule is not None:
                item.rule["group"] = group or GROUP
            found.append(item)
    return found


def _line_index(text: str) -> list[int]:
    return [m.start() for m in re.finditer(r"\n", text)]


def _commands_with_lines(text: str, newlines: list[int]):
    """split_commands, with the line each one starts on."""
    import bisect
    pos, depth, start, i = 0, 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ";\n" and not (ch == "\n" and _continues(text, i)):
            piece = text[start:i].strip()
            if piece:
                lead = start + (len(text[start:i]) - len(text[start:i].lstrip()))
                yield piece, bisect.bisect_right(newlines, lead - 1) + 1
            start = i + 1
        i += 1
    piece = text[start:].strip()
    if piece:
        lead = start + (len(text[start:]) - len(text[start:].lstrip()))
        yield piece, bisect.bisect_right(newlines, lead - 1) + 1


def _one(name: str, args: list[str], ctx: _Context, where: str, first: str) -> Found | None:
    vars_ = ctx.vars_
    notes: list[str] = []
    try:
        if name == "alias" and len(args) >= 2:
            word, body = args[0], args[1]
            if re.match(r"_|\.(pre|post)_", word):
                # 3kdb's hooks: its bot calls them, nobody types them.
                return Found("skip", where, first, why="a 3kdb hook, called by "
                             "3kdb's own bot rather than typed")
            actions = translate_body(body, ctx, True, notes)
            if not actions:
                raise _Unsupported("nothing in it this can send")
            uses_args = re.search(r"%\d", body)
            ends_plain = not split_commands(body)[-1].lstrip().startswith("#")
            if re.fullmatch(r"[^\s%{}()^$\\]+", word):
                if not uses_args and ends_plain and actions[-1]["type"] == "send":
                    # tt++ puts what you typed after the alias on the end.
                    actions[-1] = {"type": "send", "text": actions[-1]["text"] + " {args}"}
                rule = {"kind": "alias", "mode": "command", "pattern": word,
                        "name": word, "actions": actions}
            else:
                regex, why = translate(word)
                if regex is None:
                    raise _Unsupported(why)
                rule = {"kind": "alias", "mode": "regex",
                        "pattern": ("" if regex.startswith("^") else "^") + regex
                        + ("" if regex.endswith("$") else "$"),
                        "name": word, "actions": actions}
            return Found("alias", where, first, rule, notes=notes)
        if name == "action" and len(args) >= 2:
            pattern, body = args[0], args[1]
            actions = translate_body(body, ctx, False, notes)
            if not actions:
                raise _Unsupported("nothing in it this can send")
            if plain_text(pattern):
                rule = {"kind": "trigger", "mode": "contains", "pattern": pattern,
                        "actions": actions}
            else:
                regex, why = translate(pattern)
                if regex is None:
                    raise _Unsupported(why)
                rule = {"kind": "trigger", "mode": "regex", "pattern": regex,
                        "actions": actions}
            return Found("trigger", where, first, rule, notes=notes)
        if name == "gag" and args:
            pattern = args[0]
            if plain_text(pattern):
                rule = {"kind": "trigger", "mode": "contains", "pattern": pattern,
                        "gag": True, "actions": []}
            else:
                regex, why = translate(pattern)
                if regex is None:
                    raise _Unsupported(why)
                rule = {"kind": "trigger", "mode": "regex", "pattern": regex,
                        "gag": True, "actions": []}
            return Found("gag", where, first, rule)
        if name == "ticker" and len(args) >= 3:
            label, body, secs = args[0], args[1], _var(args[2], vars_)
            try:
                every = float(secs)
            except ValueError:
                raise _Unsupported(f"a ticker every {secs!r}") from None
            if every < MIN_EVERY:
                raise _Unsupported(f"every {every:g}s is faster than the game's beat")
            actions = translate_body(body, ctx, False, notes)
            if not actions:
                raise _Unsupported("nothing in it this can send")
            rule = {"kind": "timer", "name": label, "every": every, "actions": actions}
            return Found("timer", where, first, rule, notes=notes)
        if name in ("alias", "action", "ticker", "gag"):
            need = {"alias": 2, "action": 2, "ticker": 3, "gag": 1}[name]
            return Found("skip", where, first, why=f"#{name} with {len(args)} of the "
                         f"{need} parts it needs -- not read")
        if name in ("highlight", "substitute"):
            return Found("skip", where, first, why=f"#{name}: the client has no "
                         "equivalent yet")
        if name == "macro":
            return Found("skip", where, first, why="#macro: set keys under Options -> Keyboard")
        return None
    except _Unsupported as why:
        kind = {"alias": "alias", "action": "trigger", "ticker": "timer",
                "gag": "gag"}.get(name, name)
        return Found("skip", where, first, why=f"{kind} uses {why}")


# --- for the page, and bringing them in -----------------------------------------------

def _key(rule: dict) -> tuple:
    """What makes two rules the same one: importing a file twice adds nothing."""
    if "path" in rule:
        return ("route", (rule.get("name") or "").lower())
    if rule.get("kind") == "timer":
        return ("timer", (rule.get("name") or "").lower())
    return (rule.get("kind"), rule.get("mode"), rule.get("pattern"), bool(rule.get("gag")))


def _have(rules, routes) -> set:
    have = {_key({"kind": r.kind, "mode": r.mode, "pattern": r.pattern,
                  "gag": r.gag, "name": r.name}) for r in rules}
    return have | {("route", r.name.lower()) for r in (routes or [])}


def preview(files: list[tuple[str, str]], existing, routes=None, rooms=None) -> dict:
    """What Import would do, for the page: every item, numbered."""
    have = _have(existing, routes)
    items = []
    earlier: dict[tuple, str] = {}
    for n, f in enumerate(read(files, rooms)):
        key = _key(f.rule) if f.rule else None
        notes = list(f.notes)
        again = key is not None and key not in have and key in earlier
        if again:
            # The same rule twice in one file: Import adds it once, so the
            # count here says so rather than promising both.
            notes.insert(0, f"the same as {earlier[key]}")
        elif key is not None:
            earlier.setdefault(key, f.source)
        items.append({"id": n, "kind": f.kind, "source": f.source, "text": f.text,
                      "why": f.why, "notes": notes, "rule": f.rule,
                      "have": bool(key and (key in have or again))})
    counts: dict[str, int] = {}
    for it in items:
        k = "already there" if it["have"] else it["kind"]
        counts[k] = counts.get(k, 0) + 1
    return {"items": items, "counts": counts}


def bring_in(files: list[tuple[str, str]], ids, store, routes=None,
             rooms=None) -> tuple[int, list[str]]:
    """Add the chosen items: rules to the rules, paths to the routes.
    How many, and any it could not."""
    wanted = set(ids)
    have = _have(store.rules, routes.routes if routes is not None else None)
    added, problems = 0, []
    for n, f in enumerate(read(files, rooms)):
        if n not in wanted or f.rule is None or _key(f.rule) in have:
            continue
        if f.kind == "route":
            if routes is None:
                problems.append(f"{f.source}: routes are not available")
                continue
            _route, problem = routes.upsert(dict(f.rule))
        else:
            rule, problem = store.upsert(dict(f.rule))
        if problem:
            problems.append(f"{f.source}: {problem}")
            continue
        have.add(_key(f.rule))
        added += 1
    return added, problems
