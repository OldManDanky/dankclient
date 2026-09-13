"""Who is in your party, read from what 3K says about it.

A stepper in a room with somebody else in it has one question: is that a
partymate, whose kill is ours to share, or a stranger, whose mob we leave
alone?  3K's room data does not say -- a player there offers `exa`, `follow`
and `say hi` whoever they are -- and no MIP record lists a party.  So the
list is kept from 3K's own words:

* `pwho`, which prints a table, one row per member::

      Name         Location                                  Creator
      Friend       The Center of Town (e,w,s,n,d,omp,jump)  (mud        )

  A table replaces the list outright: it is 3K's word on the party now.
* `[PARTY] Friend joins the party.`, `... has quit the party.` and
  `... has been booted from the party.`, which keep it current in between.
  When the one quitting or booted is you, you have no party left.
* anybody talking on the Party channel, who is in it by definition.

Names are compared without case: 3K capitalises a name in a room and in
`pwho`, and writes it in lower case in `New leader for the party: friend.`
"""

from __future__ import annotations

import re
import time
from typing import Callable

#: The first line of `pwho`'s answer.
HEADER = re.compile(r"^\s*Name\s+Location\s+Creator\s*$")
#: A member's row: the name, then the wide gap before the location.
ROW = re.compile(r"^\s*([A-Za-z][\w'-]*)\s{2,}\S")
JOINS = re.compile(r"\[PARTY\]\s+(\w+) joins the party\.")
LEAVES = re.compile(r"\[PARTY\]\s+(\w+) (?:has quit|has been booted from) the party\.")


class Party:
    def __init__(self, me: Callable[[], str] = lambda: "",
                 clock: Callable[[], float] = time.monotonic) -> None:
        #: Members, lower case, you included once 3K has said so.
        self.members: set[str] = set()
        self._me = me
        self._clock = clock
        #: A `pwho` table being read: the rows so far, or None.
        self._table: list[str] | None = None
        #: Bumped whenever the list changes, so a waiter can see an answer land.
        self.version = 0
        #: When a stepper last sent `pwho`, so it does not ask in every room.
        self.asked_at: float | None = None

    def has(self, name: str) -> bool:
        return name.strip().lower() in self.members

    def asked(self) -> None:
        self.asked_at = self._clock()

    def since_asked(self) -> float:
        return float("inf") if self.asked_at is None else self._clock() - self.asked_at

    # --- reading 3K ------------------------------------------------------------

    def line(self, text: str) -> None:
        """One line of output."""
        text = (text or "").rstrip()
        if self._table is not None:
            row = ROW.match(text)
            if row and not HEADER.match(text):
                self._table.append(row.group(1).lower())
                return
            # Anything else -- the prompt, a blank line -- ends the table.
            self._set(set(self._table))
            self._table = None
        if HEADER.match(text):
            self._table = []
            return
        self._event(text)

    def chat(self, chat) -> None:
        """A channel record.  Somebody talking on the Party channel is in it."""
        if (getattr(chat, "channel", "") or "").lower() != "party":
            return
        message = getattr(chat, "message", "") or ""
        who = (getattr(chat, "who", "") or "").strip().lower()
        # 3K's own announcements carry a speaker too, and it may be the one
        # who just left -- "Lost our leader!" after a quit -- so only somebody
        # actually talking on the channel is counted in by it.
        if who and who not in self.members and "[PARTY]" not in message:
            self._set(self.members | {who})
        self._event(message)

    def _event(self, text: str) -> None:
        joined = JOINS.search(text)
        if joined:
            self._set(self.members | {joined.group(1).lower()})
            return
        left = LEAVES.search(text)
        if left:
            name = left.group(1).lower()
            if name == (self._me() or "").lower():
                self._set(set())               # it is you who is out
            else:
                self._set(self.members - {name})

    def _set(self, members: set[str]) -> None:
        if members != self.members:
            self.members = members
        self.version += 1
