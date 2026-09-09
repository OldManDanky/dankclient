#!/usr/bin/env python3
"""Draw the application icon.

Windows shows a generic executable box for anything without one -- in the
Start Menu, on the taskbar, in Apps & Features -- and a program that looks
like every other unlabelled program is one people lose.

The mark is the map panel at icon size: four rooms, and the one you are
standing in lit.  It is the most recognisable thing the client draws, it reads
at sixteen pixels, and it is the same drawing as the page's favicon.

No image library -- zlib writes the PNGs and an ICO is a header and a table of
offsets, so this is stdlib like everything else.  Drawn at four times the size
and averaged down, which is what gives the curves their edges.

    python3 tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

#: Straight from the page's palette, so the icon and the interface agree.
GROUND = (0x0D, 0x0F, 0x13)
ROOM = (0x39, 0x40, 0x4F)
LIT = (0x6F, 0x9B, 0xEB)

#: Sizes Windows asks for.  16 is the taskbar and the title bar, 256 is the
#: one Explorer scales down from.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Everything below is in sixteenths, so one drawing serves every size.
CORNER = 3.0
ROOMS = ((3, 3, False), (9, 3, False), (3, 9, False), (9, 9, True))
ROOM_SIZE, ROOM_CORNER = 4.0, 1.0

OVER = 4          # supersampling; 4x4 samples a pixel


def inside_round_rect(x, y, left, top, size, radius) -> bool:
    dx = max(left + radius - x, 0.0, x - (left + size - radius))
    dy = max(top + radius - y, 0.0, y - (top + size - radius))
    if x < left or y < top or x > left + size or y > top + size:
        return False
    return dx * dx + dy * dy <= radius * radius


def pixels(size: int) -> bytes:
    """RGBA rows, top down, with a one-byte filter marker on each."""
    scale = size / 16.0
    rows = []
    for py in range(size):
        row = bytearray(b"\x00")                 # PNG filter: none
        for px in range(size):
            r = g = b = a = 0
            for sy in range(OVER):
                for sx in range(OVER):
                    x = (px + (sx + 0.5) / OVER) / scale
                    y = (py + (sy + 0.5) / OVER) / scale
                    if not inside_round_rect(x, y, 0, 0, 16, CORNER):
                        continue
                    colour = GROUND
                    for rx, ry, lit in ROOMS:
                        if inside_round_rect(x, y, rx, ry, ROOM_SIZE,
                                             ROOM_CORNER):
                            colour = LIT if lit else ROOM
                            break
                    r += colour[0]
                    g += colour[1]
                    b += colour[2]
                    a += 255
            n = OVER * OVER
            # Averaged over every sample, including the ones that fell outside
            # -- which is what rounds the corner off rather than stepping it.
            row += bytes((r // n, g // n, b // n, a // n))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    head = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)   # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", head)
            + chunk(b"IDAT", zlib.compress(pixels(size), 9))
            + chunk(b"IEND", b""))


def ico(sizes=SIZES) -> bytes:
    images = [png(s) for s in sizes]
    # ICONDIR, then one ICONDIRENTRY each, then the images themselves.
    offset = 6 + 16 * len(images)
    out = [struct.pack("<HHH", 0, 1, len(images))]
    for size, body in zip(sizes, images):
        out.append(struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,       # 0 means 256
            0 if size >= 256 else size,
            0, 0, 1, 32, len(body), offset))
        offset += len(body)
    return b"".join(out + images)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else HERE / "mud" / "ui" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = ico()
    out.write_bytes(body)
    print(f"  {out}  {len(body)} bytes, sizes {', '.join(map(str, SIZES))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
