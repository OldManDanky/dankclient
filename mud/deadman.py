"""The deadman: once nobody has typed for a while, nothing automated goes out.

3K expects a person to be playing.  A stepper left walking with nobody at the
keyboard keeps walking into whatever changed while nobody was looking.  So:
fifteen minutes without a command typed by a person, and the steppers pause
where they are and nothing automated is sent -- no triggers, no timers, no
script sends.  The first command typed brings it all back, and the steppers
carry on from where they stopped.

Fifteen minutes is fixed.  It is the game's rule, not a preference, so there
is nothing to set and no way to switch it off.

What is held back is dropped rather than saved up: somebody coming back to
their keyboard should not be greeted by twenty stale commands going out at
once.  Logging back in after a link death and the MIP handshake are not held:
they keep the connection, they are not playing the character.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

#: Minutes without a typed command before everything automated pauses.
MINUTES = 15.0


class Deadman:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[bool], None] | None = None) -> None:
        self.minutes = MINUTES
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
        if not self._tripped and self.idle() >= self.minutes * 60:
            self._tripped = True
            self._free.clear()
            if self.on_change:
                self.on_change(True)
        return self._tripped

    def idle(self) -> float:
        """Seconds since somebody last typed a command."""
        return self._clock() - self._last

    async def wait(self) -> None:
        """Hold a stepper here for as long as it is tripped."""
        while self.tripped:
            await self._free.wait()

    def state(self) -> dict:
        return {"minutes": self.minutes, "tripped": self.tripped}

    def _release(self) -> None:
        self._tripped = False
        self._free.set()
        if self.on_change:
            self.on_change(False)
