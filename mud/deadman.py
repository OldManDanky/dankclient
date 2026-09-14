"""The deadman: once nobody has typed for a while, nothing automated goes out.

3K expects a person to be playing.  A stepper left walking with nobody at the
keyboard keeps walking into whatever changed while nobody was looking.  So:
fifteen minutes, by default, without a command typed by a person, and the
steppers pause where they are, and timers and anything else the client would
send of its own accord are dropped.  Triggers still answer what 3K says -- the
corpse trigger after the kill a stepper was in the middle of -- but nothing
they send is a move, or a trigger would be a stepper by another name (see
`outbound.answering`).  The first command typed brings it all back, and the
steppers carry on from where they stopped.

The time can be set from 1 to 15 minutes, or 0 for off.  Never longer than
fifteen: that is the game's rule.

What is held back is dropped rather than saved up: somebody coming back to
their keyboard should not be greeted by twenty stale commands going out at
once.  Logging back in after a link death and the MIP handshake are not held:
they keep the connection, they are not playing the character.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

#: The most minutes without a typed command before everything automated
#: pauses, and the default.  3K's rule: nothing sets it longer.
MINUTES = 15.0
#: The least it can be set to without being off.
LEAST = 1.0
#: Off.
OFF = 0.0


def allowed(minutes) -> float:
    """A time the deadman may have: 0 (off), or 1 to 15 minutes.

    Anything that is not a number, or is below 0, is fifteen; anything longer
    is fifteen too.
    """
    try:
        minutes = float(minutes)
    except (TypeError, ValueError):
        return MINUTES
    if minutes == OFF:
        return OFF
    if not minutes > 0:                 # also NaN
        return MINUTES
    return min(MINUTES, max(LEAST, minutes))


class Deadman:
    def __init__(self, minutes: float = MINUTES,
                 clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[bool], None] | None = None) -> None:
        self.minutes = allowed(minutes)
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
        if not self._tripped and self.minutes > OFF \
                and self.idle() >= self.minutes * 60:
            self._tripped = True
            self._free.clear()
            if self.on_change:
                self.on_change(True)
        return self._tripped

    def idle(self) -> float:
        """Seconds since somebody last typed a command."""
        return self._clock() - self._last

    def set_minutes(self, minutes) -> float:
        """Change the time: 0 (off) or 1-15 minutes.  Switched off, or given
        longer, it lets go now.

        Changing it is a person at the Options page, but it does not start the
        count again: only a typed command does that.
        """
        self.minutes = allowed(minutes)
        if self._tripped and (self.minutes == OFF
                              or self.idle() < self.minutes * 60):
            self._release()
        return self.minutes

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
