"""The game tick.

3k.org runs on a 2-second beat and announces it twice over, neither of which
is guaranteed:

  * composite tag N is a combat round counter -- exact, but only while fighting
  * tag E (guild points) advances on the same beat while regenerating, which
    stops when guild points are capped

Measured over a live session: N at median 2.01s, E-only composites at median
2.00s across 205 samples.  So lock onto whichever signal is present and
free-run when neither is, rather than trusting either one.
"""

from __future__ import annotations

import asyncio
import time

PERIOD = 2.0            # seconds, 3k.org
DRIFT = 1.25            # free-run once a signal is this many periods late


class Clock:
    def __init__(self, period: float = PERIOD) -> None:
        self.period = period
        self.source = "free"        # "round" | "regen" | "free"
        self.ticks = 0
        self.last = 0.0
        self._event = asyncio.Event()
        self._task: asyncio.Task | None = None

    # --- observation --------------------------------------------------------

    def observe(self, source: str) -> None:
        """A tick was witnessed on the wire."""
        now = time.monotonic()
        if self.last and 0.5 < now - self.last < 6.0:
            # gentle EMA; the server beat is fixed, so don't chase jitter
            self.period += 0.1 * ((now - self.last) - self.period)
        self.last = now
        self.source = source
        self.ticks += 1
        self._event.set()

    # --- waiting ------------------------------------------------------------

    async def wait(self) -> None:
        """Return at the next tick, real or free-run."""
        self._event.clear()
        timeout = self.period * DRIFT
        if self.last:
            elapsed = time.monotonic() - self.last
            timeout = max(0.05, self.period * DRIFT - elapsed)
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except asyncio.TimeoutError:
            self.source = "free"
            self.last = time.monotonic()
            self.ticks += 1

    def start(self, bus) -> None:
        """Drive TICK events off the observed beat."""
        from . import events

        async def pump() -> None:
            while True:
                await self.wait()
                bus.emit(events.TICK)

        self._task = asyncio.ensure_future(pump())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
