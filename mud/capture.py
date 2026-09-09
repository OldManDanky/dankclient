"""Session capture: raw bytes plus a timing index.

The ``.bin`` file is the byte stream exactly as it arrived, so it can be
replayed through the scanner verbatim.  Timestamps live in a sidecar ``.idx``
rather than being interleaved, which keeps the stream pure::

    run.bin     <raw bytes>
    run.idx     "<seconds since start> <offset> <length>" per read
    run.out     "<seconds since start>\t<line>" per command we sent

Timing matters for questions the bytes alone can't answer -- notably whether
the FFF composite arrives on a cadence or only when a value changes, which
decides whether round timing can be derived from it.

What we sent lives in its own file rather than being spliced into the stream,
for the same reason the timestamps do: the ``.bin`` has to stay the MUD's
bytes and nothing else.  A shared clock is what puts the two back in order.

That ordering is the whole basis of mapping.  The MUD never says "you moved",
and movement is not a closed vocabulary -- ``climb pipe`` moves you between
rooms and appears in no exit list.  The only thing that identifies a move is
that we sent something and a room block came back, so a capture without the
commands cannot be mapped, replayed or debugged after the fact.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator


class CaptureWriter:
    def __init__(self, stem: str | Path) -> None:
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite a capture -- they are irreplaceable and re-running
        # with the same --log stem used to silently destroy the last session.
        base, n = stem, 1
        while base.with_suffix(".bin").exists():
            base = stem.with_name(f"{stem.name}-{n}")
            n += 1
        stem = base
        self.bin_path = stem.with_suffix(".bin")
        self.idx_path = stem.with_suffix(".idx")
        self.out_path = stem.with_suffix(".out")
        self._bin = self.bin_path.open("wb")
        self._idx = self.idx_path.open("w")
        self._out = self.out_path.open("w")
        self._offset = 0
        self._t0 = time.monotonic()

    def _stamp(self) -> str:
        return f"{time.monotonic() - self._t0:.3f}"

    def write(self, chunk: bytes) -> None:
        self._bin.write(chunk)
        self._idx.write(f"{self._stamp()} {self._offset} {len(chunk)}\n")
        self._offset += len(chunk)

    def sent(self, line: str) -> None:
        """Record a line on its way to the MUD."""
        self._out.write(f"{self._stamp()}\t{_escape(line)}\n")

    def flush(self) -> None:
        self._bin.flush()
        self._idx.flush()
        self._out.flush()

    def close(self) -> None:
        self.flush()
        self._bin.close()
        self._idx.close()
        self._out.close()


def read_capture(path: str | Path) -> Iterator[tuple[float | None, bytes]]:
    """Yield (timestamp, chunk) pairs, replaying reads as they happened."""
    path = Path(path)
    data = path.with_suffix(".bin").read_bytes()
    idx = path.with_suffix(".idx")

    if not idx.exists():
        yield None, data
        return

    for line in idx.read_text().splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        ts, offset, length = float(parts[0]), int(parts[1]), int(parts[2])
        yield ts, data[offset : offset + length]


# A command is one line by construction, but a paste or a script can put a
# newline or a tab in one, and either would silently split the record.
_CODES = {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _escape(line: str) -> str:
    return "".join(_CODES.get(c, c) for c in line)


def _unescape(text: str) -> str:
    out, it = [], iter(text)
    for c in it:
        if c != "\\":
            out.append(c)
            continue
        nxt = next(it, "")
        out.append({"n": "\n", "r": "\r", "t": "\t"}.get(nxt, nxt))
    return "".join(out)


def read_commands(path: str | Path) -> Iterator[tuple[float, str]]:
    """Yield (timestamp, line) for everything the client sent."""
    out = Path(path).with_suffix(".out")
    if not out.exists():
        return
    for raw in out.read_text().splitlines():
        ts, sep, line = raw.partition("\t")
        if not sep:
            continue
        try:
            yield float(ts), _unescape(line)
        except ValueError:
            continue


def replay(path: str | Path) -> Iterator[tuple[str, float | None, bytes | str]]:
    """Both halves of a session in the order they happened.

    Yields ``("recv", t, chunk)`` and ``("sent", t, line)``.  Sends come first
    at equal timestamps: a reply cannot precede the command that caused it, and
    the mapper's whole rule is that the outstanding command owns the next room
    block.
    """
    reads = [("recv", ts, chunk) for ts, chunk in read_capture(path)]
    sends = [("sent", ts, line) for ts, line in read_commands(path)]
    if any(ts is None for _, ts, _ in reads):      # no index: no interleaving
        yield from reads
        yield from sends
        return
    yield from sorted(reads + sends, key=lambda e: (e[1], e[0] == "recv"))
