"""3kdb's gags: a library of lines to keep off the screen, a group at a time.

3kdb carries seven hundred-odd tt++ `#gag` lines in `common/gags/`, grouped
the way its own `gags` alias switches them: area monsters, guild combat,
item spam, the ray-gun, and the rest.  They come in through Options ->
Updates like the map and the bots -- data, never executed -- and every group
starts *off*.  A gag hides text, and a line somebody wanted to read going
missing without their say is worse than any amount of spam.  Which groups
are on belongs to the character, beside their other gags.

Only `#gag` lines are taken.  The `#act`s in the same files are scripts --
priorities, one-shot actions, a banner that announces Ewell -- and are left
where they are.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import set_aside, write_atomically
from .triggers import Trigger

#: The library, shared: 3kdb's, rewritten whole by each update.
LIBRARY = "gags-3kdb.json"
#: Which groups one character has switched on.
ENABLED = "gag-groups.json"
#: Who owns the gags in the session's set, so a group can be taken out whole.
OWNER = "3kdb-gags"

#: file -> key, what to call it, and what it hides.  In the order worth reading.
GROUPS = [
    ("gags.tin", "basics", "Blank lines and prompts",
     "Empty lines, a bare > prompt, and the weight-recalculation notice."),
    ("gags_combat.tin", "combat", "Combat: general",
     "Eternal, monster-skill and profession spam."),
    ("gags_area.tin", "area", "Combat: area monsters",
     "What particular areas' monsters say and do at you, area by area."),
    ("gags_combat_guild.tin", "guild", "Combat: guilds",
     "Guild attack messages, guild by guild."),
    ("gags_combat_items.tin", "items", "Combat: items",
     "Spammy weapons and items."),
    ("gags_raygun.tin", "raygun", "Ray-gun",
     "Every message the ray-gun makes."),
]

GAG = re.compile(r"^\s*#gag\s*\{(.*)\}\s*;?\s*$", re.I)
HEADING = re.compile(r"^\s*#nop\s*--\s*(.+?)\s*;?\s*$", re.I)
CAPTURE = re.compile(r"\d{1,2}")


def translate(pattern: str) -> str | None:
    r"""A tt++ pattern as a Python regex, or None if it uses something else.

    What 3kdb's gags actually use: ^ and $ to anchor, %* for anything, %w a
    word, %d a number, %s and %S space and not-space, %1..%99 a capture --
    written %%1 inside an alias, which is the same thing -- and braces, whose
    contents tt++ hands straight to its regex engine: {Tugs|Hugs}, {.|!}, or
    a whole pattern like {^The Spork Lance GASHES (.*)\!}.  Everything else
    is text.  Any other % code is not guessed at: that gag is left out, and
    counted.
    """
    out: list[str] = []
    i, end = 0, len(pattern)
    anchored_end = pattern.endswith("$") and not pattern.endswith("\\$")
    if anchored_end:
        end -= 1
    if pattern.startswith("^"):
        out.append("^")
        i = 1
    while i < end:
        c = pattern[i]
        if c == "{":
            close = pattern.find("}", i + 1)
            if close < 0 or close > end:
                return None
            out.append(f"(?:{pattern[i + 1:close]})")
            i = close + 1
            continue
        if c == "%" and pattern.startswith("%%", i):
            i += 1                        # %%1 in an alias is %1
            continue
        if c == "%" and i + 1 < end + (1 if anchored_end else 0):
            code = pattern[i + 1]
            simple = {"*": ".*", "w": r"\w+", "d": r"\d+", "s": r"\s+", "S": r"\S+"}
            if code in simple:
                out.append(simple[code])
                i += 2
                continue
            digits = CAPTURE.match(pattern, i + 1)
            if digits:
                out.append(".*?")
                i = digits.end()
                continue
            return None
        if c == "}":
            return None
        out.append(re.escape(c))
        i += 1
    if anchored_end:
        out.append("$")
    regex = "".join(out)
    try:
        re.compile(regex)
    except re.error:
        return None
    return regex


def parse(text: str) -> tuple[list[dict], int]:
    """The gags in one of 3kdb's files, with the heading each sits under."""
    gags, skipped, section = [], 0, ""
    for line in text.splitlines():
        head = HEADING.match(line)
        if head:
            section = head.group(1).strip()
            continue
        hit = GAG.match(line)
        if not hit:
            continue
        pattern = hit.group(1)
        regex = translate(pattern)
        if regex is None:
            skipped += 1
            continue
        gags.append({"pattern": pattern, "regex": regex, "section": section})
    return gags, skipped


def import_gags(root: Path, into: Path) -> dict:
    """Read 3kdb's gag files under `root` and write the library to `into`."""
    folder = Path(root) / "common" / "gags"
    groups, total, skipped = [], 0, 0
    for name, key, title, what in GROUPS:
        path = folder / name
        if not path.exists():
            continue
        gags, missed = parse(path.read_text(encoding="latin-1"))
        if not gags:
            continue
        sections = list(dict.fromkeys(g["section"] for g in gags if g["section"]))
        groups.append({"key": key, "title": title, "what": what, "file": name,
                       "sections": sections, "gags": gags, "skipped": missed})
        total += len(gags)
        skipped += missed
    write_atomically(Path(into), json.dumps({"groups": groups}, indent=1))
    return {"groups": len(groups), "gags": total, "skipped": skipped}


def load_library(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"groups": []}
    try:
        got = json.loads(path.read_text())
        if not isinstance(got, dict) or not isinstance(got.get("groups"), list):
            raise ValueError("not a gag library")
    except (ValueError, OSError):
        set_aside(path)
        return {"groups": []}
    return got


def load_enabled(path: Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    try:
        got = json.loads(path.read_text())
        return {str(k) for k in got.get("on", [])} if isinstance(got, dict) else set()
    except (ValueError, OSError):
        set_aside(path)
        return set()


def save_enabled(path: Path, on) -> None:
    write_atomically(Path(path), json.dumps({"on": sorted(on)}, indent=1))


def _hide(*_args, **_kwargs) -> None:
    """A gag does nothing when it matches; the screen's gate is the point."""


def apply(gags, library: dict, on) -> int:
    """Put the groups that are on into the session's gags, and only those."""
    gags.remove_owner(OWNER)
    added = 0
    for group in library.get("groups", []):
        if group.get("key") not in on:
            continue
        for g in group.get("gags", []):
            try:
                gags.add(Trigger(g["regex"], _hide, "regex", OWNER))
                added += 1
            except (KeyError, re.error):
                continue
    return added
