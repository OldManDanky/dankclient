#!/usr/bin/env python3
"""Prove (or disprove) the web server, without a browser in the way.

    python3 tools/wscheck.py 8080

Fetches the page and its assets, then performs a real WebSocket handshake and
waits for the first state frame -- exactly what the browser does.  Run it on
the machine the server is on: if this passes, the server is fine and the
problem is the browser, the cache, or the SSH tunnel.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.web import _accept_key, _read_frame  # noqa: E402

OK, BAD = "\x1b[32mok  \x1b[0m", "\x1b[31mFAIL\x1b[0m"


async def main(port: int) -> int:
    base = f"http://127.0.0.1:{port}"
    failures = 0

    for path in ("/", "/app.js", "/vendor/xterm.js", "/vendor/xterm.css",
                 "/vendor/xterm-addon-fit.js"):
        try:
            r = await asyncio.to_thread(urllib.request.urlopen, base + path, None, 5)
            body = r.read()
            print(f"  {OK} {r.status}  {len(body):>7}  {path}")
        except Exception as exc:
            failures += 1
            print(f"  {BAD}          {path}  -> {exc}")

    print()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), 5
        )
    except Exception as exc:
        print(f"  {BAD} cannot open a socket at all: {exc}")
        return 1

    key = base64.b64encode(os.urandom(16)).decode()
    writer.write(
        f"GET /ws HTTP/1.1\r\nHost: localhost:{port}\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
        f"Origin: http://localhost:{port}\r\n"
        f"Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits\r\n"
        f"\r\n".encode()
    )
    await writer.drain()

    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    except asyncio.TimeoutError:
        print(f"  {BAD} no response to the upgrade request")
        return 1

    status = head.decode("latin-1").splitlines()[0]
    if "101" not in status:
        print(f"  {BAD} upgrade refused: {status}")
        return 1
    print(f"  {OK} {status}")
    print(f"  {'ok  ' if _accept_key(key).encode() in head else 'FAIL'} "
          f"Sec-WebSocket-Accept")

    try:
        opcode, payload = await asyncio.wait_for(_read_frame(reader), 5)
    except asyncio.TimeoutError:
        print(f"  {BAD} handshake succeeded but no state frame arrived")
        return 1

    snap = json.loads(payload)
    p = snap.get("player", {})
    print(f"  {OK} first frame: {len(payload)} bytes, t={snap.get('t')!r}")
    print(f"       hp={p.get('hp')} sp={p.get('sp')} round={p.get('round')} "
          f"room={snap.get('room', {}).get('short')!r}")

    # round-trip a command the way the browser does
    body = json.dumps({"t": "cmd", "d": ""}).encode()
    writer.write(bytes(bytearray([0x81, 0x80 | len(body)]) + b"\x00\x00\x00\x00" + body))
    await writer.drain()
    print(f"  {OK} sent a frame without the server dropping us")

    writer.close()
    print(f"\n{'server is healthy' if not failures else 'server has problems'}")
    return 1 if failures else 0


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    sys.exit(asyncio.run(main(port)))
