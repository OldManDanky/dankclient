"""Outbound commands, governed by actions per minute.

3k.org measures APM -- non-directional commands entered per minute -- and
takes an interest above 100.  That is the real constraint, and it is much
looser than the combat round: 100/min is 1.67 commands per second, where one
command per 2s round would be 30/min.  Pacing everything to the round is three
times more conservative than the rule it was trying to respect, and it adds up
to two seconds of latency to a single trigger firing a single command.

So: send immediately, and throttle only as the minute budget gets tight.

Movement is free.  Compass directions and the exits of the room you are
standing in do not count against APM, which matters because walking is most of
what an automated session does -- and we know the exits, because DDD tells us.

Two paths remain separate: what a human types goes out at once and is counted;
what scripts send is governed.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections import deque
from typing import Callable, Iterable

#: lower sorts first
PANIC, HIGH, NORMAL, LOW = -100, -10, 0, 10

#: how a command relates to the governor
NOW = "now"          # send at once, ignore the budget
PACED = "paced"      # send at once unless the minute is tight  (default)
ROUND = "round"      # at most one per combat round, always queued
PACES = (NOW, PACED, ROUND)

#: Movement, which 3k.org does not count.  Room exits are added at runtime.
DIRECTIONS = {
    "n", "s", "e", "w", "ne", "nw", "se", "sw", "u", "d",
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
    "up", "down", "in", "out", "enter", "exit", "leave",
}


class APMMeter:
    """Rolling count of non-directional commands over the last minute."""

    def __init__(self, limit: int = 100, soft: int = 80, window: float = 60.0):
        self.limit = limit
        #: start throttling here, leaving headroom for what the player types
        self.soft = soft
        self.window = window
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
        return True

    def rate(self) -> int:
        cutoff = time.monotonic() - self.window
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()
        return len(self._stamps)

    def headroom(self) -> int:
        """How many more actions fit under the soft limit."""
        return max(0, self.soft - self.rate())


class SendQueue:
    def __init__(self, send: Callable[[str], None], clock, *,
                 apm: APMMeter | None = None,
                 exits: Callable[[], Iterable[str]] = tuple,
                 per_tick: int = 3, panic_immediate: bool = True,
                 ready=None):
        self._send = send
        #: Is there a socket to send down?  Anything put while there is not
        #: waits in the heap for one, rather than raising at the caller.
        self.ready = ready or (lambda: True)
        self._clock = clock
        self.apm = apm or APMMeter()
        self.exits = exits
        #: most a backlog may drain per tick, still subject to the budget
        self.per_tick = per_tick
        self.panic_immediate = panic_immediate
        self._heap: list[tuple[int, int, str]] = []
        self._seq = itertools.count()
        self._task: asyncio.Task | None = None
        self.sent = 0
        self.dropped = 0

    def __len__(self) -> int:
        return len(self._heap)

    @property
    def pending(self) -> list[str]:
        return [line for _, _, line in sorted(self._heap)]

    # --- sending ------------------------------------------------------------

    def now(self, line: str) -> None:
        """Send at once.  Still counted -- the budget is about the MUD's view."""
        self._send(line)
        self.apm.record(line, self.exits())
        self.sent += 1

    def put(self, line: str, priority: int = NORMAL, pace: str = PACED) -> None:
        # Nothing goes out while there is no socket -- it waits.  A rule that
        # fires on a disconnect would otherwise reach `now`, which raises, and
        # the rule would look broken rather than pending.  Coming back is
        # exactly when "send this" should happen.
        if not self.ready():
            heapq.heappush(self._heap, (priority, next(self._seq), line))
            return
        if pace == NOW or (self.panic_immediate and priority <= PANIC):
            self.now(line)
            return
        if pace != ROUND and not self._heap and self.apm.headroom() > 0:
            self.now(line)
            return
        heapq.heappush(self._heap, (priority, next(self._seq), line))

    def flush(self) -> int:
        n = len(self._heap)
        self._heap.clear()
        self.dropped += n
        return n

    # --- draining -----------------------------------------------------------

    async def run(self) -> None:
        while True:
            await self._clock.wait()
            for _ in range(self.per_tick):
                if not self._heap or self.apm.headroom() <= 0:
                    break
                if not self.ready():
                    break
                _, _, line = heapq.heappop(self._heap)
                self.now(line)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self.run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
