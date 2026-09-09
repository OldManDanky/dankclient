"""Turn the byte stream into lines, and strip ANSI for matching.

Triggers must match what the player *sees*, not what the wire carries.  3k.org
colours things mid-token -- "<cChi Focus>" style markup in guild lines, ANSI in
ordinary output -- so a pattern written against the visible text silently stops
matching the moment a wizard adds colour to a name.  Match on the stripped
copy; keep the styled one for rendering.
"""

from __future__ import annotations

import re

#: CSI sequences plus OSC strings.  Deliberately broad: anything we fail to
#: strip becomes an invisible character inside somebody's regex.
_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"      # CSI ... final byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL / ST
    r"|\x1b[@-Z\\-_]"                  # two-character escapes
)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


class LineAssembler:
    """Accumulates byte chunks and emits complete lines.

    MUD output does not arrive in line units -- a line can span reads, and a
    prompt arrives with no newline at all.
    """

    def __init__(self, encoding: str = "latin-1") -> None:
        self.encoding = encoding
        self._buf = ""

    @property
    def partial(self) -> str:
        """Whatever has arrived since the last newline (usually the prompt)."""
        return self._buf

    def feed(self, data: bytes | str) -> list[tuple[str, str]]:
        """Return [(raw, plain)] for each complete line."""
        if isinstance(data, bytes):
            data = data.decode(self.encoding, "replace")
        self._buf += data

        out: list[tuple[str, str]] = []
        while True:
            idx = self._buf.find("\n")
            if idx < 0:
                break
            raw = self._buf[:idx].rstrip("\r")
            self._buf = self._buf[idx + 1:]
            out.append((raw, strip_ansi(raw)))
        return out
