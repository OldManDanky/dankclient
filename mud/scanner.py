"""MIP wire-protocol scanner.

Frames Messaging Interface Protocol messages out of a raw MUD byte stream.

The scanner is deliberately character-at-a-time and holds its state across
``feed()`` calls.  This is how Portal itself does it (MUDAnsi.pas:1808) and it
is the only approach that survives what 3k.org actually sends:

  * messages arrive back-to-back with no separator of any kind::

        #K%12345003DDD#K%12345083HAAnpc~Marble Monolith~...

  * a message may be split across TCP segments at any byte -- a client that
    buffers by line leaks the tail of one onto the screen, which is exactly
    what "WARNING: Someone has been idle for 6H 21M.i Focus>: <gNormal>" is.
  * payloads may contain newlines of their own.

So neither line boundaries nor packet boundaries mean anything.  The 3-digit
character count is the only delimiter there is.

Header layout::

    #K%  12345      068        FFF   J~G2N: <y81094877>...
    ^    ^          ^          ^     ^
    |    |          |          |     `- data, ~-delimited
    |    |          |          `------- line code, 3 chars
    |    |          `------------------ char count: covers CODE **and** DATA
    |    `----------------------------- security code, 5 digits
    `---------------------------------- ACTIVATE literal

Anything that fails to parse is emitted as ordinary text and the offending
byte is re-read from NORMAL, so a player typing "#K%" in a tell can never
desync us.  Every abort emits at least one byte, which guarantees progress.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

MAGIC = b"#K%"
SEC_LEN = 3 + 5          # offset of the char count within a header
LEN_LEN = 3
CODE_LEN = 3

DELIM = "~"
ESCAPED_DELIM = "^^"     # undocumented; see codes.unescape()


@dataclass(frozen=True)
class Text:
    """Ordinary MUD output, verbatim (ANSI still embedded)."""

    data: bytes


@dataclass(frozen=True)
class Message:
    """One framed MIP message."""

    sec: str
    code: str
    data: str

    def __repr__(self) -> str:  # keeps capture logs readable
        return f"<MIP {self.code} {self.data!r}>"


Event = Text | Message


class _S(enum.Enum):
    NORMAL = 0
    MAGIC = 1
    SEC = 2
    LEN = 3
    BODY = 4
    #: just finished one, deciding whether the next bytes are its own line
    #: ending or the start of something to show
    ENDING = 5
    ENDING_CR = 6


def _is_digit(b: int) -> bool:
    return 0x30 <= b <= 0x39


class Scanner:
    """Incremental MIP framer.  Feed it bytes, get back Text/Message events."""

    def __init__(self, *, encoding: str = "latin-1") -> None:
        self.encoding = encoding
        # bytes consumed toward a possible message; replayed verbatim on abort
        self._raw = bytearray()
        self._sec = bytearray()
        self._len = bytearray()
        self._body = bytearray()
        self._need = 0
        # confirmed-ordinary bytes, coalesced so we don't emit one event per char
        self._text = bytearray()
        self._state = _S.NORMAL

    @property
    def in_message(self) -> bool:
        """True when a partial message is buffered awaiting more bytes.

        Not while deciding what follows a finished one: nothing is held back
        there but at most a carriage return, and the message itself has
        already been handed over.
        """
        return self._state not in (_S.NORMAL, _S.ENDING, _S.ENDING_CR)

    def feed(self, chunk: bytes) -> list[Event]:
        out: list[Event] = []
        i, n = 0, len(chunk)

        while i < n:
            b = chunk[i]
            st = self._state

            if st is _S.NORMAL:
                if b == MAGIC[0]:
                    self._state = _S.MAGIC
                    self._raw.append(b)
                else:
                    self._text.append(b)
                i += 1

            elif st is _S.MAGIC:
                if b != MAGIC[len(self._raw)]:
                    self._abort()
                    continue                    # re-read this byte as text
                self._raw.append(b)
                if len(self._raw) == len(MAGIC):
                    self._state = _S.SEC
                i += 1

            elif st is _S.SEC:
                if not _is_digit(b):
                    self._abort()
                    continue
                self._raw.append(b)
                self._sec.append(b)
                if len(self._raw) == SEC_LEN:
                    self._state = _S.LEN
                i += 1

            elif st is _S.LEN:
                if not _is_digit(b):
                    self._abort()
                    continue
                self._raw.append(b)
                self._len.append(b)
                i += 1
                if len(self._len) == LEN_LEN:
                    need = int(self._len)
                    if need < CODE_LEN:
                        # impossible: the count always covers the 3-char code
                        self._abort()
                        continue
                    self._need = need
                    self._state = _S.BODY

            elif st is _S.ENDING:
                # 3K ends every message with a line of its own.  The message
                # is ours and the newline is the message's, so passing it on
                # printed a blank line into the terminal for every one of them
                # -- and the ones that keep coming while nothing is happening
                # are the regen composites, twice a beat, for ever.
                if b == 0x0A:                       # \n
                    i += 1
                    self._state = _S.NORMAL
                elif b == 0x0D:                     # \r, its \n may follow
                    i += 1
                    self._state = _S.ENDING_CR
                else:
                    self._state = _S.NORMAL         # re-read from NORMAL

            elif st is _S.ENDING_CR:
                if b == 0x0A:
                    i += 1
                else:
                    # A carriage return on its own after a message is not a
                    # line ending, so it was text: give it back.
                    self._text.append(0x0D)
                self._state = _S.NORMAL

            else:  # _S.BODY
                self._raw.append(b)
                self._body.append(b)
                i += 1
                if len(self._body) == self._need:
                    self._flush_text(out)
                    out.append(
                        Message(
                            sec=self._sec.decode("ascii"),
                            code=self._body[:CODE_LEN].decode(self.encoding),
                            data=self._body[CODE_LEN:].decode(self.encoding),
                        )
                    )
                    self._reset()
                    self._state = _S.ENDING

        self._flush_text(out)
        return out

    def _abort(self) -> None:
        """Not a MIP header after all: give the bytes back as ordinary text.

        The current byte is deliberately *not* consumed -- it is re-read from
        NORMAL, mirroring Portal's ``dec(i)``.  ``_raw`` is always non-empty
        here, so the loop always makes progress.
        """
        self._text += self._raw
        self._reset()

    def _flush_text(self, out: list[Event]) -> None:
        if self._text:
            out.append(Text(bytes(self._text)))
            self._text.clear()

    def _reset(self) -> None:
        self._state = _S.NORMAL
        self._raw.clear()
        self._sec.clear()
        self._len.clear()
        self._body.clear()
        self._need = 0
