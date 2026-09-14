"""Outbound commands: sent at once, and counted.

3k.org measures APM -- non-directional commands entered per minute -- and
watches for more than 100.  The client used to hold automated commands back
as the minute filled.  It no longer does: 3K's admins would rather a player
knew they had gone over than have the client quietly slow them down.  So the
count is shown in the Session panel, and reaching the limit says so, once
(`APMMeter.on_over`).

Movement is free.  Compass directions and the exits of the room you are
standing in do not count, which matters because walking is most of what an
automated session does -- and we know the exits, because DDD tells us.

What still waits: anything put while there is no socket (it goes when there is
one, unless it has gone stale), a command paced to the combat round, and
anything behind one of those, so that nothing overtakes it.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterable

#: lower sorts first
PANIC, HIGH, NORMAL, LOW = -100, -10, 0, 10

#: how a command relates to what is already waiting
NOW = "now"          # send at once, ahead of anything waiting
PACED = "paced"      # send at once unless the minute is tight  (default)
ROUND = "round"      # at most one per combat round, always queued
PACES = (NOW, PACED, ROUND)

#: How long a queued command may wait before it has lost its moment.  A minute:
#: a line that could not go out inside a whole minute was never going to
#: arrive in time to mean anything.  It is the deadman's rule, applied to the
#: clock instead of the keyboard -- and it is what stops a disconnection from
#: keeping a night of timers and firing them all when the socket comes back.
STALE = 60.0

#: Is what is being sent an answer to something 3K just said -- a trigger, an
#: event, a watch -- rather than the client acting of its own accord, as a
#: timer or a stepper does?  The deadman lets answers through, but never a
#: move: a corpse trigger after a kill is support, a trigger that walks on
#: "Obvious exits" is a stepper.  A context variable, so a task started while
#: answering (a rule's wait, a script's coroutine) is still answering; a
#: stepper clears it for itself.
ANSWERING: ContextVar[bool] = ContextVar("answering", default=False)


@contextmanager
def answering(yes: bool = True):
    """Mark what is sent inside as an answer to 3K (or, with False, not)."""
    token = ANSWERING.set(yes)
    try:
        yield
    finally:
        ANSWERING.reset(token)

#: Movement, which 3k.org does not count.  Room exits are added at runtime.
DIRECTIONS = {
    "n", "s", "e", "w", "ne", "nw", "se", "sw", "u", "d",
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
    "up", "down", "in", "out", "enter", "exit", "leave",
}


class APMMeter:
    """Rolling count of non-directional commands over the last minute.

    It counts and it tells; it holds nothing back.  Reaching `limit` calls
    `on_over` once, and it is armed again when the minute has dropped back
    under `soft` -- one warning per busy spell, not one per command in it.
    """

    def __init__(self, limit: int = 100, soft: int = 80, window: float = 60.0,
                 on_over: Callable[[int], None] | None = None):
        self.limit = limit
        #: where the Session panel's bar turns amber, and a warning re-arms
        self.soft = soft
        self.window = window
        self.on_over = on_over
        self._over = False
        self._stamps: deque[float] = deque()

    @staticmethod
    def is_directional(line: str, exits: Iterable[str] = ()) -> bool:
        word = line.strip().split(" ")[0].lower()
        if not word:
            return True                    # a blank line is not an action
        return word in DIRECTIONS or word in {e.lower() for e in exits}

    def record(self, line: str, exits: Iterable[str] = ()) -> bool:
        """Count it unless it was movement.  True if it counted."""
        if self.is_directional(line, exits):
            return False
        self._stamps.append(time.monotonic())
        count = self.rate()
        if not self._over and count >= self.limit:
            self._over = True
            if self.on_over is not None:
                self.on_over(count)
        return True

    def rate(self) -> int:
        cutoff = time.monotonic() - self.window
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()
        if self._over and len(self._stamps) < self.soft:
            self._over = False                  # calmed down: warn again next time
        return len(self._stamps)



class SendQueue:
    def __init__(self, send: Callable[[str], None], clock, *,
                 apm: APMMeter | None = None,
                 exits: Callable[[], Iterable[str]] = tuple,
                 per_tick: int = 3, panic_immediate: bool = True,
                 ready=None, held=None, stale: float = STALE, now=None,
                 on_stale=None):
        self._send = send
        #: Is there a socket to send down?  Anything put while there is not
        #: waits in the heap for one, rather than raising at the caller.
        self.ready = ready or (lambda: True)
        #: Has the deadman tripped?  Then nothing automated goes out but an
        #: answer that is not a move, and nothing is kept for later either.
        self.held = held or (lambda: False)
        self._clock = clock
        self.apm = apm or APMMeter()
        self.exits = exits
        #: most a backlog may drain per tick
        self.per_tick = per_tick
        self.panic_immediate = panic_immediate
        #: how long a line may wait before it is dropped instead of sent
        self.stale = stale
        self._now = now or time.monotonic
        #: (priority, seq, queued at, answering, line).  The line stays last so
        #: that reading it as the last field goes on working; seq already
        #: makes every entry unique, so nothing is ever compared past it.
        self._heap: list[tuple[int, int, float, bool, str]] = []
        self._seq = itertools.count()
        self._task: asyncio.Task | None = None
        self.sent = 0
        self.dropped = 0
        #: dropped for having waited too long, counted apart from the rest
        self.went_stale = 0
        #: told how many, when it happens.  Commands disappearing without a
        #: word is its own puzzle -- "my ticks stopped working".
        self.on_stale = on_stale

    def __len__(self) -> int:
        return len(self._heap)

    @property
    def pending(self) -> list[str]:
        return [line for *_, line in sorted(self._heap)]

    # --- sending ------------------------------------------------------------

    def now(self, line: str) -> None:
        """Send at once, and count it: the count is 3K's view, whoever sent it."""
        self._send(line)
        self.apm.record(line, self.exits())
        self.sent += 1

    def auto_now(self, line: str) -> None:
        """Send at once, for a script rather than a person: held like put()."""
        if self._held(line, ANSWERING.get()):
            self.dropped += 1
            return
        self.now(line)

    def put(self, line: str, priority: int = NORMAL, pace: str = PACED) -> None:
        if self._held(line, ANSWERING.get()):
            # Nobody has typed for a while: nothing automated goes out, and it
            # is dropped rather than saved -- twenty stale commands going out
            # the moment somebody comes back is the opposite of the point.
            self.dropped += 1
            return
        # Nothing goes out while there is no socket -- it waits.  A rule that
        # fires on a disconnect would otherwise reach `now`, which raises, and
        # the rule would look broken rather than pending.  Coming back is
        # exactly when "send this" should happen.
        if not self.ready():
            self._hold(priority, line)
            return
        if pace == NOW or (self.panic_immediate and priority <= PANIC):
            self.now(line)
            return
        # At once -- unless something is already waiting, which it must not
        # overtake.  APM is counted, never waited for.
        if pace != ROUND and not self._heap:
            self.now(line)
            return
        self._hold(priority, line)

    def _held(self, line: str, answer: bool) -> bool:
        """Does the deadman keep this back?  While it has tripped, everything
        but an answer to 3K that is not a move."""
        if not self.held():
            return False
        return not answer or self.apm.is_directional(line, self.exits())

    def _hold(self, priority: int, line: str) -> None:
        heapq.heappush(self._heap, (priority, next(self._seq), self._now(),
                                    ANSWERING.get(), line))

    def flush(self) -> int:
        n = len(self._heap)
        self._heap.clear()
        self.dropped += n
        return n

    def drop_automated(self) -> int:
        """The deadman has tripped: drop what waits, keeping only answers."""
        keep = [item for item in self._heap if not self._held(item[-1], item[3])]
        gone = len(self._heap) - len(keep)
        if gone:
            self._heap[:] = keep
            heapq.heapify(self._heap)
            self.dropped += gone
        return gone

    # --- draining -----------------------------------------------------------

    def drop_stale(self) -> int:
        """Throw away what has waited longer than it was worth.

        Everything, not just the head: a backlog drains in priority order, so
        the stale lines are not necessarily the ones in the way.
        """
        cutoff = self._now() - self.stale
        keep = [item for item in self._heap if item[2] >= cutoff]
        gone = len(self._heap) - len(keep)
        if gone:
            self._heap[:] = keep
            heapq.heapify(self._heap)
            self.dropped += gone
            self.went_stale += gone
            if self.on_stale is not None:
                self.on_stale(gone)
        return gone

    def drain_once(self) -> None:
        """One beat's worth: drop what went stale, then send what is waiting."""
        self.drop_stale()
        for _ in range(self.per_tick):
            if not self._heap:
                break
            if not self.ready():
                break
            if self.held():
                # Only an answer goes while the deadman has tripped.
                free = [item for item in self._heap
                        if not self._held(item[-1], item[3])]
                if not free:
                    break
                item = min(free)
                self._heap.remove(item)
                heapq.heapify(self._heap)
            else:
                item = heapq.heappop(self._heap)
            self.now(item[-1])

    async def run(self) -> None:
        while True:
            await self._clock.wait()
            self.drain_once()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self.run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
