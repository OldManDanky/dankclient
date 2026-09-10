"""Gags: lines that never reach the screen.

tt++'s `#gag {string}` removes any line containing the string, and a 3K
player has a list of them for the spam they have stopped wanting to read.  A
gag here is the same, and only the screen loses the line: it still reaches the
triggers and the log, which is also how tt++ does it -- gagging a line is not
a reason for the rule that reacts to it to stop working.

The difficulty is that the screen is fed in network chunks rather than lines.
A line can arrive in two reads, and deciding about it needs all of it, so
while there are gags a line is held until its newline arrives.  3K marks
nothing as a prompt -- not one telnet GA or EOR in 59 captures -- and a
prompt has no newline, so the unfinished line is shown after a tenth of a
second instead of waiting for one that is not coming.  If the rest of it
turns up later and is gagged after all, the part already drawn is wiped.

With no gags at all nothing is held, and the stream reaches the screen exactly
as it did before any of this existed.
"""

from __future__ import annotations

from typing import Callable

from .lines import strip_ansi

#: How long an unfinished line may wait for the rest of it.
HOLD = 0.1

#: Back to the start of the row and clear it: the part of a line already on
#: screen, taken back off when the rest of it turns out to be gagged.
ERASE = b"\r\x1b[2K"


class LineGate:
    """Between the stream and the screen: whole lines, minus the gagged ones."""

    def __init__(self, gagged: Callable[[str], bool], encoding: str = "latin-1",
                 active: Callable[[], bool] = lambda: True) -> None:
        self.gagged = gagged
        self.encoding = encoding
        #: Are there any gags?  When not, nothing is held.
        self.active = active
        self.reset()

    def reset(self) -> None:
        self._held = b""        # the unfinished line, not shown yet
        self._shown = b""       # the unfinished line, already on screen
        self._gagging = False   # the line so far is gagged; so is the rest

    @property
    def pending(self) -> bool:
        return bool(self._held)

    def feed(self, chunk: bytes) -> bytes:
        """A chunk of the stream; returns what may be drawn now."""
        out = bytearray()
        buf, self._held = self._held + chunk, b""
        while True:
            end = buf.find(b"\n")
            if end < 0:
                break
            line, buf = buf[:end + 1], buf[end + 1:]
            if self._gagging or (self.active() and self._gag(self._shown + line)):
                if self._shown and not self._gagging:
                    out += ERASE          # its start is on screen already
            else:
                out += line
            self._shown, self._gagging = b"", False
        if buf:
            if self.active():
                self._held = buf          # until the rest arrives, or release()
            elif not self._gagging:
                out += buf
                self._shown += buf
        return bytes(out)

    def release(self) -> bytes:
        """Stop waiting for the end of the unfinished line: show it, or not."""
        held, self._held = self._held, b""
        if not held or self._gagging:
            return b""
        if self.active() and self._gag(self._shown + held):
            # A prompt that is gagged, or a line whose gagged part has already
            # arrived.  The rest of the line goes with it.
            self._gagging = True
            return ERASE if self._shown else b""
        self._shown += held
        return held

    def _gag(self, raw: bytes) -> bool:
        plain = strip_ansi(raw.decode(self.encoding, "replace")).rstrip("\r\n")
        return bool(self.gagged(plain))
