"""Bringing CMUD settings across: its XML export.

CMUD is zMUD's successor, and its export is XML rather than lines:

    <cmud><window name="3k">
      <class name="areas" enabled="false">
        <trigger priority="10" regex="true" case="true">
          <pattern>(\\w+) tells you: *</pattern>
          <value>#WA 500
    kill undead</value>
        </trigger>
        <alias name="gk" autoappend="true"><value>kill %1</value></alias>
      </class>
    </window></cmud>

The language inside is zMUD's, so this reads the XML and hands every rule to
zmimport's builders; what CMUD adds is said outright rather than guessed:

* classes nest, and one switched off switches off everything in it;
* `regex="true"` is a regex, not zMUD's pattern language; `case="true"`
  keeps capitals (otherwise, as zMUD, they are ignored);
* `autoappend="true"` puts what was typed on the end of every command in an
  alias until one uses an argument (zMUD, always on, put it on the last
  command only), and its absence does not;
* a line break between commands is as good as `;`;
* its own direction definitions (`<dir name="h" dir="nw">`) say h j k l are
  nw ne sw se -- what the map had already shown for zMUD.

A trigger with further states (CMUD's multi-state triggers), a Wait, Loop or
Expression trigger, and anything in a window of CMUD's own -- a Tells window
with `host="none"` -- does not come across, and is listed with the reason.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import zmimport as zm
from .ttimport import Found


def is_cmud(text: str) -> bool:
    return "<cmud" in text[:4000].lower()


def _commands(value: str) -> str:
    """CMUD's commands with the line breaks between them made `;`."""
    out, depth = [], 0
    for ch in value.replace("\r\n", "\n").strip():
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        out.append(";" if ch == "\n" and depth == 0 else ch)
    return "".join(out)


def _value(e) -> str:
    v = e.find("value")
    return (v.text if v is not None else e.text) or ""


def read(files: list[tuple[str, str]], rooms=None) -> list[Found]:
    found: list[Found] = []
    for fname, text in files:
        # ElementTree will not take a str that still declares its encoding.
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            found.append(Found("skip", fname, fname, why=f"not XML this can read ({exc})"))
            continue
        found += _read_one(fname, root, rooms)
    return found


def _read_one(fname: str, root, rooms) -> list[Found]:
    classes: list[str] = []
    items: list[tuple[str, object, str, bool, str]] = []

    def walk(e, path: str, on: bool, window: str) -> None:
        for c in e:
            if c.tag == "class":
                p = f"{path}|{c.get('name', '')}" if path else c.get("name", "")
                classes.append(p)
                walk(c, p, on and c.get("enabled") != "false", window)
            elif c.tag == "window":
                # A window of CMUD's own -- somewhere tells were captured to --
                # has no host; its rules act on that window, not on the game.
                walk(c, "", True, c.get("name", "") if c.get("host") == "none" else "")
            elif c.tag in ("trigger", "alias", "var", "macro", "button", "path"):
                items.append((c.tag, c, path, on and c.get("enabled") != "false", window))
    walk(root, "", True, "")

    vars_: dict[str, str] = {}
    changed: set[str] = set()
    aliases: dict[str, str] = {}
    ids: list[str] = []
    for tag, e, _p, _on, _w in items:
        if tag == "var" and e.find("json") is None:
            vars_[e.get("name", "").lstrip("'").lower()] = _value(e).strip()
        elif tag == "alias":
            aliases[e.get("name", "").lower()] = _commands(_value(e))
        elif tag == "trigger" and e.get("name"):
            ids.append(e.get("name"))
        if tag in ("trigger", "alias"):
            changed |= zm.changed_vars(_value(e))
    for name in changed:
        vars_.pop(name, None)
    ctx = zm.Context(vars_, aliases, classes, ids)

    out: list[Found] = []
    for tag, e, klass, on, window in items:
        where = f"{fname} · {zm.group_of(klass) or 'no class'}"
        pattern = e.findtext("pattern") or ""
        first = (f"<alias {e.get('name')}>" if tag == "alias"
                 else f"<trigger> {pattern}"[:120] if tag == "trigger"
                 else f"<{tag} {e.get('name') or e.get('key') or ''}>")
        if tag == "var":
            continue                        # a value, not a rule
        if window:
            out.append(Found("skip", where, first, why=f"belongs to CMUD's own "
                             f"{window!r} window, not to the game"))
            continue
        if tag == "macro":
            out.append(Found("skip", where, first, why="a key: set keys under "
                             "Options -> Keyboard"))
            continue
        if tag == "button":
            out.append(Found("skip", where, first, why="a button: the client has "
                             "no buttons of your own yet"))
            continue
        if tag == "path":
            out.append(zm._route(e.get("name", ""), _commands(_value(e)), ctx,
                                 where, first, rooms))
            continue
        if tag == "alias":
            out.append(zm.alias_found(e.get("name", ""), _commands(_value(e)), klass, on,
                                      ctx, where, first,
                                      append="every" if e.get("autoappend") == "true" else False))
            continue
        # a trigger
        kind = e.get("type")
        if e.find("trigger") is not None:
            out.append(Found("skip", where, first, why="trigger with further states "
                             "(CMUD's multi-state triggers)"))
            continue
        if kind == "Alarm":
            out.append(zm.alarm_found(pattern, _commands(_value(e)), klass, on,
                                      ctx, where, first))
            continue
        if kind:
            out.append(Found("skip", where, first, why=f"a {kind!r} trigger, which "
                             "the client has no equivalent of"))
            continue
        case = e.get("case") == "true"
        if e.get("regex") == "true":
            # CMUD's regex ignores capitals unless told otherwise, and the way
            # to tell it -- on its forum, not in its help -- is (?-i) in front.
            if pattern.startswith("(?-i)"):
                pattern, case = pattern[5:], True
            regex = ("" if case else "(?i)") + pattern
            try:
                re.compile(regex)
            except re.error as exc:
                out.append(Found("skip", where, first, why=f"trigger uses a regex "
                                 f"Python cannot read ({exc})"))
                continue
        else:
            regex, why = zm.translate(pattern, case)
            if regex is None:
                out.append(Found("skip", where, first, why=f"trigger uses {why}"))
                continue
        out.append(zm.trigger_found(regex, _commands(_value(e)), klass, on,
                                    ctx, where, first))
    return out
