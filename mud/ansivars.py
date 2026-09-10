"""The character's own colour settings, kept before this client changes them.

Somebody trying this client sets its line markers on their character, and the
markers stay there when they go back to the client they had: every room title
arrives wrapped in ``-R-_``, and whatever colours they had chosen for those
lines are gone.  So the settings are read first and kept, to be put back.

3K has no command that lists them as values.  What it has is a help page,
``ansivars``, that draws each variable's name *in* that variable's colours --
prefix, name, suffix -- which is the value, if it is read off the raw line
before anything strips it::

    ESC[34;1mattackESC[0m           Damage and hits that you do
    -M-_look_monsterESC[0m     Monsters you see
    attacked         Damage and hits done to you

It is paged, forty lines at a time, and the pager waits for a key: the reader
answers it.  ("ansi vars", with a space, is not a command: 3K says "No such
color vars.")
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .paths import set_aside, write_atomically

COMMAND = "ansivars"
RESET = "\x1b[0m"
#: 3K marks no prompt, so the page is over when it has been quiet this long
QUIET = 1.5
#: and given up on after this, however it is going
MOST = 30.0

#: The variables 3K's page listed, longest first so that "attacked" is never
#: read as "attack" and a prefix.  Only a help to finding the name in a line
#: that also holds its colours -- one not here is still read.
KNOWN = sorted((
    "armour", "attack", "attacked", "gossip", "kill", "look_monster",
    "look_weapon", "look_object", "look_armor", "look_armour", "look_player",
    "look_other", "look_item", "hidemelee", "notify", "party", "room_exits",
    "room_long", "room_short", "say", "spouse", "shout", "soul", "soul2",
    "tell", "watch", "wimpy",
), key=len, reverse=True)

#: The look_* markers this client set on its first pass (see prefixes.AFTER)
FIRST_PASS = ("-M-_", "-P-_", "-w-", "-a-", "-o-", "-i-")

#: "More: 0-39(42) : [q,b,<cr>] " -- the pager, waiting for a key
MORE = re.compile(r"More: \d+-\d+\(\d+\)\s*:\s*\[")
#: the pager's prompt left at the front of the next line
MORE_LEAD = re.compile(r"^.*?More: [^\]]*\]\s*(?:\x1b\[[0-9;]*m)?")
ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
#: a name with its colours, two or more spaces, and what it is for
ROW = re.compile(r"^(\S+?)\s{2,}(\S.*)$")
WORD = re.compile(r"[a-z][a-z0-9_]*[a-z0-9]")


def parse_line(raw: str) -> tuple[str, str, str] | None:
    """(name, prefix, suffix) from one raw line of the page, or None."""
    raw = MORE_LEAD.sub("", raw).rstrip()
    row = ROW.match(raw)
    if not row:
        return None
    head = row.group(1)
    found = _name_in(head)
    if found is None:
        return None
    at, name = found
    return name, head[:at], head[at + len(name):]


def _name_in(head: str) -> tuple[int, str] | None:
    """Where the variable's name is in its own colours: never inside an escape."""
    spans, last = [], 0
    for esc in ESCAPE.finditer(head):
        spans.append((last, esc.start()))
        last = esc.end()
    spans.append((last, len(head)))

    def fits(at: int, word: str) -> bool:
        before = head[at - 1] if at else ""
        after = head[at + len(word):at + len(word) + 1]
        return not (before.isalnum() and before.islower() or before.isdigit()
                    or after.isalnum() and after.islower() or after.isdigit())

    for word in KNOWN:
        for start, end in spans:
            at = head.find(word, start, end)
            if at >= 0 and fits(at, word):
                return at, word
    best = None
    for start, end in spans:
        for m in WORD.finditer(head, start, end):
            if len(m.group(0)) >= 3 and (best is None or len(m.group(0)) > len(best[1])):
                best = (m.start(), m.group(0))
    return best


def touched(prefixes) -> list[str]:
    """The variables this client's settings change, by name."""
    names = []
    for var, _ in prefixes.pairs:
        names.append(re.sub(r"_(pref|suff)$", "", var))
    for command in prefixes.after:
        parts = command.split()
        if len(parts) >= 2 and parts[0] == prefixes.verb:
            names.append(re.sub(r"_(pref|suff)$", "", parts[1]))
    return list(dict.fromkeys(names))


def shown(command: str) -> str:
    """A command as it can be printed: an escape on screen would be obeyed."""
    return command.replace("\x1b", "<ESC>")


class AnsiVars:
    """Reads 3K's page when asked, and keeps what it said, per character."""

    #: how many readings are kept -- the one before this client matters most,
    #: and it is never the newest for long
    KEEP = 20

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.saved: list[dict] = []
        self._rows: dict | None = None
        self._tail = ""
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict) or not isinstance(raw.get("saved"), list):
                raise ValueError("not a list of readings")
        except (ValueError, OSError):
            set_aside(self.path)
            return
        self.saved = [s for s in raw["saved"]
                      if isinstance(s, dict) and isinstance(s.get("vars"), dict)]

    def save(self) -> None:
        write_atomically(self.path, json.dumps({"saved": self.saved}, indent=2))

    # --- reading the page ---------------------------------------------------

    @property
    def reading(self) -> bool:
        return self._rows is not None

    def begin(self) -> None:
        self._rows, self._tail = {}, ""

    def line(self, raw: str) -> None:
        if self._rows is None:
            return
        got = parse_line(raw)
        if got:
            name, pref, suff = got
            self._rows[name] = {"pref": pref, "suff": suff}

    def more(self, text: str) -> bool:
        """Is the pager waiting?  Watched across reads: its prompt can split."""
        if self._rows is None:
            return False
        self._tail = (self._tail + ESCAPE.sub("", text))[-200:]
        if MORE.search(self._tail):
            self._tail = ""
            return True
        return False

    def end(self, who: str = "", when: float | None = None) -> dict | None:
        """Stop reading, and keep what was read.  None if nothing was."""
        rows, self._rows, self._tail = self._rows, None, ""
        if not rows:
            return None
        snap = {"when": time.strftime("%Y-%m-%d %H:%M",
                                      time.localtime(when or time.time())),
                "who": who, "vars": rows}
        self.saved = (self.saved + [snap])[-self.KEEP:]
        self.save()
        return snap

    # --- putting them back --------------------------------------------------

    @staticmethod
    def ours(snap: dict, markers) -> bool:
        """Was this read after this client's markers were already set?

        Its first pass set the look_* markers too, before they turned out to
        stop HAA; a reading that has those is not one to go back to either.
        """
        marks = [m for m in (*markers, *FIRST_PASS) if m]
        return any(m in v.get("pref", "") or m in v.get("suff", "")
                   for v in snap["vars"].values() for m in marks)

    def own(self, markers) -> dict | None:
        """The newest reading from before this client's markers went on."""
        for snap in reversed(self.saved):
            if not self.ours(snap, markers):
                return snap
        return None

    @staticmethod
    def restore(snap: dict, names, verb: str = "aset") -> list[str]:
        """The commands that put `names` back the way `snap` found them.

        Nothing on the page means nothing set, which reads the same on screen
        as a reset -- and a reset is the form 3K takes.
        """
        out = []
        for name in names:
            v = snap["vars"].get(name)
            if v is None:
                continue
            pref, suff = v.get("pref") or RESET, v.get("suff") or RESET
            if pref == RESET and suff == RESET:
                out.append(f"{verb} {name} reset")
            else:
                out += [f"{verb} {name}_pref {pref}", f"{verb} {name}_suff {suff}"]
        return out

    def summary(self, markers) -> dict:
        def brief(snap):
            return snap and {"when": snap["when"], "vars": len(snap["vars"]),
                             "ours": self.ours(snap, markers)}
        return {"reading": self.reading, "count": len(self.saved),
                "latest": brief(self.saved[-1] if self.saved else None),
                "own": brief(self.own(markers))}
