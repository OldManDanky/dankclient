"""Text triggers -- the fallback path.

With MIP carrying hit points, guild state, room contents, tells and chat as
structured fields, most of what people write regex for on other MUDs is
unnecessary here.  This is for the long tail: quest text, guild messages, and
anything not wired into the protocol.

Two things keep it cheap and safe:

  * a literal prefilter.  Most patterns contain a fixed substring, so bucket by
    it and check with a hash lookup before running any regex.  500 triggers
    against 200 lines/second is 100k regex evaluations; the prefilter turns
    almost all of them into nothing.
  * that same prefilter is most of the ReDoS mitigation.  Python's re cannot be
    interrupted mid-match -- sys.settrace does not fire inside C -- so a
    catastrophic pattern would hang the client.  Rarely running the regex at
    all is the cheap defence; `regex` with a timeout is the upgrade path.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

_QUANT = "?*{"
_META = set(".^$*+?{}[]\\|()")


def literal_hint(pattern: str) -> str | None:
    """Longest fixed substring a candidate line must contain, or None.

    Must understand enough regex syntax not to mistake structure for text:
    treating "(?P<who>" as literal would have us searching lines for "P<who>",
    which matches nothing and silently disables the trigger.
    """
    best = cur = ""
    i, n = 0, len(pattern)

    def flush(b: str, c: str) -> tuple[str, str]:
        return (max(b, c, key=len), "")

    while i < n:
        c = pattern[i]

        if c == "\\":                       # escape: \w, \d, \., ...
            best, cur = flush(best, cur)
            i += 2
        elif c == "[":                       # character class
            best, cur = flush(best, cur)
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":  # a literal ] may lead the class
                j += 1
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            i = j + 1
        elif c == "(":                       # group, incl. (?P<name> and (?:
            best, cur = flush(best, cur)
            if pattern.startswith("(?P<", i):
                close = pattern.find(">", i)
                i = close + 1 if close > 0 else i + 4
            elif pattern.startswith("(?", i):
                i += 2
                while i < n and pattern[i] in ":=!<P":
                    i += 1
            else:
                i += 1
        elif c == "{":                       # {m,n}
            best, cur = flush(best, cur)
            close = pattern.find("}", i)
            i = close + 1 if close > 0 else i + 1
        elif c in "*+?":                     # the preceding char is optional
            cur = cur[:-1]
            best, cur = flush(best, cur)
            i += 1
        elif c in ".^$|)":
            best, cur = flush(best, cur)
            i += 1
        else:
            cur += c
            i += 1

    best, _ = flush(best, cur)
    best = best.strip()
    return best if len(best) >= 3 else None


@dataclass
class Trigger:
    pattern: str
    fn: Callable
    mode: str = "regex"          # "command" | "contains" | "glob" | "regex"
    owner: str = ""
    priority: int = 0
    stop: bool = False           # consume the line, skip lower-priority ones
    regex: re.Pattern | None = field(default=None, repr=False)
    literal: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.mode == "command":
            # An alias is a verb you type.  Match the first word exactly and
            # hand the rest over as {args}, which is what "gk orc" needs and
            # what a substring match cannot give you.
            self.literal = None          # matching is cheap; no prefilter needed
            self.pattern = self.pattern.strip()
        elif self.mode == "contains":
            self.literal = self.pattern
        elif self.mode == "glob":
            # Each * captures, so actions can use {1}, {2}, ...  A trailing *
            # is greedy so it takes the rest of the line rather than matching
            # the empty string.
            parts = self.pattern.split("*")
            chunks = [re.escape(parts[0])]
            for i, part in enumerate(parts[1:], start=1):
                trailing = i == len(parts) - 1 and part == ""
                chunks.append("(.*)" if trailing else "(.*?)")
                chunks.append(re.escape(part))
            self.regex = re.compile("".join(chunks))
            self.literal = max(parts, key=len).strip() or None
            if self.literal and len(self.literal) < 3:
                self.literal = None
        else:
            self.regex = re.compile(self.pattern)
            # Flags at the front are not text: "(?i)" would lend its "i".
            self.literal = literal_hint(re.sub(r"^\(\?[aiLmsux]+\)", "", self.pattern))
            if self.literal and self.regex.flags & re.IGNORECASE:
                # The quick check has to ignore capitals when the pattern
                # does, or "(?i)ready for battle" never sees "READY FOR
                # BATTLE" -- which was every trigger imported from zMUD.
                self.literal = self.literal.lower()
                self.fold = True

    #: Set for a pattern that ignores capitals: its literal is lower-cased,
    #: and TriggerSet checks it against the line lower-cased.
    fold: bool = False

    def match(self, plain: str):
        if self.mode == "command":
            head, _, rest = plain.strip().partition(" ")
            if head.lower() != self.pattern.lower():
                return None
            words = rest.split()
            captured: dict = {"args": rest.strip()}
            captured.update({i + 1: w for i, w in enumerate(words)})
            return captured
        if self.mode == "contains":
            return {} if self.pattern in plain else None
        m = self.regex.search(plain)
        if m is None:
            return None
        return m.groupdict() or {i + 1: g for i, g in enumerate(m.groups())} or {}


class TriggerSet:
    def __init__(self) -> None:
        self._by_literal: dict[str, list[Trigger]] = defaultdict(list)
        #: Triggers that ignore capitals, by their lower-cased literal.
        self._by_folded: dict[str, list[Trigger]] = defaultdict(list)
        self._always: list[Trigger] = []

    def _buckets(self):
        return list(self._by_literal.values()) + list(self._by_folded.values())

    def __len__(self) -> int:
        return sum(len(v) for v in self._buckets()) + len(self._always)

    def add(self, trigger: Trigger) -> Trigger:
        if trigger.literal and trigger.fold:
            self._by_folded[trigger.literal].append(trigger)
        elif trigger.literal:
            self._by_literal[trigger.literal].append(trigger)
        else:
            self._always.append(trigger)
        return trigger

    def remove_owner(self, owner: str) -> int:
        n = 0
        for bucket in self._buckets():
            before = len(bucket)
            bucket[:] = [t for t in bucket if t.owner != owner]
            n += before - len(bucket)
        before = len(self._always)
        self._always[:] = [t for t in self._always if t.owner != owner]
        return n + before - len(self._always)

    def all(self) -> list[Trigger]:
        """Every registered trigger, in priority order."""
        found = list(self._always)
        for bucket in self._buckets():
            found.extend(bucket)
        found.sort(key=lambda t: (t.priority, t.owner, t.pattern))
        return found

    def candidates(self, plain: str) -> list[Trigger]:
        found = list(self._always)
        for literal, bucket in self._by_literal.items():
            if literal in plain:
                found.extend(bucket)
        if self._by_folded:
            low = plain.lower()
            for literal, bucket in self._by_folded.items():
                if literal in low:
                    found.extend(bucket)
        found.sort(key=lambda t: t.priority)
        return found

    def fire(self, plain: str) -> list[tuple[Trigger, dict]]:
        hits = []
        for trig in self.candidates(plain):
            captured = trig.match(plain)
            if captured is None:
                continue
            hits.append((trig, captured))
            if trig.stop:
                break
        return hits
