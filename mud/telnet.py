"""Minimal telnet option filter.

MIP rides inside ordinary telnet output, so all we need is to strip IAC
sequences before the MIP scanner sees the stream -- an unfiltered 0xFF byte
would otherwise land in a payload and corrupt a character count.

Policy is to refuse every option.  That is deliberate: accepting MCCP would
hand us a zlib-compressed stream, and nothing downstream is ready for that.
Add options to ACCEPT as they become useful.
"""

from __future__ import annotations

import enum

IAC = 255
DONT, DO, WONT, WILL = 254, 253, 252, 251
SB, SE = 250, 240
GA, EOR = 249, 239

OPT_ECHO = 1
OPT_TTYPE = 24
OPT_EOR = 25
OPT_NAWS = 31

#: Options we are willing to turn on.  Empty for now, by design.
ACCEPT: set[int] = set()

#: Most of a subnegotiation worth keeping.  We refuse every option, so none
#: should arrive at all; one that starts and never ends would otherwise grow
#: this buffer for as long as the connection lasts.
SB_MOST = 4096


class _S(enum.Enum):
    DATA = 0
    IAC = 1
    NEG = 2
    SB = 3
    SB_IAC = 4


class TelnetFilter:
    """Strips telnet negotiation, returning clean bytes plus replies to send."""

    def __init__(self) -> None:
        self._state = _S.DATA
        self._cmd = 0
        self._sub = bytearray()

    def feed(self, chunk: bytes) -> tuple[bytes, bytes, list[str]]:
        """Return (clean_data, bytes_to_send_back, marker_events)."""
        out = bytearray()
        reply = bytearray()
        marks: list[str] = []

        for b in chunk:
            st = self._state

            if st is _S.DATA:
                if b == IAC:
                    self._state = _S.IAC
                else:
                    out.append(b)

            elif st is _S.IAC:
                if b == IAC:
                    out.append(IAC)             # escaped literal 0xFF
                    self._state = _S.DATA
                elif b in (DO, DONT, WILL, WONT):
                    self._cmd = b
                    self._state = _S.NEG
                elif b == SB:
                    self._sub.clear()
                    self._state = _S.SB
                else:
                    if b in (GA, EOR):
                        marks.append("prompt")  # 3K may mark prompts this way
                    self._state = _S.DATA

            elif st is _S.NEG:
                reply += self._negotiate(self._cmd, b)
                self._state = _S.DATA

            elif st is _S.SB:
                if b == IAC:
                    self._state = _S.SB_IAC
                elif len(self._sub) < SB_MOST:
                    self._sub.append(b)

            else:  # _S.SB_IAC
                if b == SE:
                    marks.append(f"sb:{self._sub[0] if self._sub else -1}")
                    self._sub.clear()
                    self._state = _S.DATA
                elif b == IAC:
                    if len(self._sub) < SB_MOST:
                        self._sub.append(IAC)
                    self._state = _S.SB
                else:
                    self._state = _S.SB

        return bytes(out), bytes(reply), marks

    @staticmethod
    def _negotiate(cmd: int, opt: int) -> bytes:
        if cmd == DO:
            return bytes((IAC, WILL if opt in ACCEPT else WONT, opt))
        if cmd == WILL:
            return bytes((IAC, DO if opt in ACCEPT else DONT, opt))
        return b""      # DONT/WONT need no answer once we have agreed
