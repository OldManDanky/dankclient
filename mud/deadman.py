"""The deadman: once nobody has typed for a while, nothing automated goes out.

A bot left walking with nobody at the keyboard is a bot that keeps walking
into whatever changed while nobody was looking.  So: fifteen minutes, by
default, without a command typed by a person, and the bots and steppers pause
where they are and nothing automated is sent -- no triggers, no timers, no
script sends.  The first command typed brings it all back, and the bots carry
on from where they stopped.

What is held back is dropped rather than saved up: somebody coming back to
their keyboard should not be greeted by twenty stale commands going out at
once.  Logging back in after a link death and the MIP handshake are not held:
they keep the connection, they are not playing the character.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

#: The default, in minutes.  0 switches it off.
DEFAULT_MINUTES = 15.0


class Deadman:
    def __init__(self, minutes: float = DEFAULT_MINUTES,
                 clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[bool], None] | None = None) -> None:
        self.minutes = max(0.0, float(minutes))
        self._clock = clock
        self._last = clock()
        self._tripped = False
        #: Set whenever things may go out; cleared while tripped.
        self._free = asyncio.Event()
        self._free.set()
        self.on_change = on_change

    def touched(self) -> None:
        """A person typed a command: start the count again, and let go."""
        self._last = self._clock()
        if self._tripped:
            self._release()

    @property
    def tripped(self) -> bool:
        """Has it been too long?  Asking is what trips it, so ask often."""
        if not self._tripped and self.minutes > 0 \
                and self.idle() >= self.minutes * 60:
            self._tripped = True
            self._free.clear()
            if self.on_change:
                self.on_change(True)
        return self._tripped

    def idle(self) -> float:
        """Seconds since somebody last typed a command."""
        return self._clock() - self._last

    def set_minutes(self, minutes: float) -> None:
        """Change the time.  Switched off, or given longer, it lets go now."""
        self.minutes = max(0.0, float(minutes))
        if self._tripped and (self.minutes <= 0
                              or self.idle() < self.minutes * 60):
            self._release()

    async def wait(self) -> None:
        """Hold a bot here for as long as it is tripped."""
        while self.tripped:
            await self._free.wait()

    def state(self) -> dict:
        return {"minutes": self.minutes, "tripped": self.tripped}

    def _release(self) -> None:
        self._tripped = False
        self._free.set()
        if self.on_change:
            self.on_change(False)
