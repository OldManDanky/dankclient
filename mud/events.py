"""One event bus, so everything downstream subscribes to the same thing.

Before this, the web UI reached into three separate callback lists on the
session and the world.  Scripts, bots, the mapper and the logger all want the
same events, and four more consumers hanging off ad-hoc lists is how that
becomes unmaintainable.

Handlers may be plain functions or coroutines; coroutines are scheduled and
never awaited by the publisher, so a slow subscriber cannot stall the socket.
A handler that raises is logged and unsubscribed-from-blame, never propagated
-- one bad script must not take the client down.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import traceback
from collections import defaultdict
from typing import Any, Callable

# --- event names -------------------------------------------------------------

TEXT = "text"            # bytes -- ordinary MUD output, ANSI intact
LINE = "line"            # (raw, plain) -- one complete line, ANSI stripped
MIP = "mip"              # scanner.Message -- a framed protocol message
STATE = "state"          # (name, new, old) -- a world field changed
ROOM = "room"            # Room -- entered a new room (contents settled)
TELL = "tell"            # codes.Tell
CHAT = "chat"            # codes.Chat
ROUND = "round"          # int -- combat round counter advanced
ENEMY = "enemy"          # str -- target changed; "" means combat ended
TICK = "tick"            # None -- the ~2s game tick
PROMPT = "prompt"        # None -- IAC GA/EOR
CONNECTED = "connected"
DISCONNECTED = "disconnected"
RETRYING = "retrying"    # float -- seconds until the next attempt to reconnect

Handler = Callable[..., Any]


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def on(self, kind: str, fn: Handler | None = None):
        """Subscribe.  Usable directly or as a decorator."""
        if fn is None:
            def deco(f: Handler) -> Handler:
                self._subs[kind].append(f)
                return f
            return deco
        self._subs[kind].append(fn)
        return fn

    def off(self, kind: str, fn: Handler) -> None:
        try:
            self._subs[kind].remove(fn)
        except ValueError:
            pass

    def clear(self, kind: str | None = None) -> None:
        if kind is None:
            self._subs.clear()
        else:
            self._subs.pop(kind, None)

    def count(self, kind: str) -> int:
        return len(self._subs.get(kind, ()))

    async def wait(self, kind: str, timeout: float | None = None) -> Any:
        """Block until the next event of this kind.

        Returns its arguments -- one value if it carries one, a tuple if
        several, None on timeout.  This is what lets a script read like the
        thing it is doing: send a direction, wait to arrive, look around.
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        def once(*args: Any) -> None:
            if not fut.done():
                fut.set_result(args[0] if len(args) == 1 else (args or None))

        self.on(kind, once)
        try:
            if timeout is None:
                return await fut
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.off(kind, once)

    def emit(self, kind: str, *args: Any) -> None:
        for fn in list(self._subs.get(kind, ())):
            try:
                result = fn(*args)
                if inspect.isawaitable(result):
                    spawn(result, f"{kind} handler")
            except Exception:
                _blame(kind, fn)


#: Tasks started by spawn() and not yet finished.  The event loop keeps only
#: weak references to tasks, so one that nothing else holds can be collected
#: halfway through -- this is what holds them.
_running: set = set()


def spawn(coro: Any, what: str = "task") -> asyncio.Task | None:
    """Run a coroutine in the background, and say so if it fails.

    Instead of asyncio.create_task, everywhere.  An exception inside a task
    nobody awaits goes nowhere: it has happened three times here that a panel
    simply sat on "working" because the code behind it had raised, and
    nothing anywhere said so.  This writes it down -- to the console, or to
    client.log when there is no console.
    """
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:
        if inspect.iscoroutine(coro):
            coro.close()            # never started; don't warn that it wasn't
        return None                 # no running loop (tests, teardown)
    _running.add(task)

    def done(t: asyncio.Task) -> None:
        _running.discard(t)
        if t.cancelled() or t.exception() is None:
            return
        exc = t.exception()
        print(f"\x1b[31m[client] {what} failed:\x1b[0m\n"
              + "".join(traceback.format_exception(exc)), file=sys.stderr)

    task.add_done_callback(done)
    return task


def _blame(kind: str, fn: Handler) -> None:
    name = getattr(fn, "__qualname__", repr(fn))
    print(f"\x1b[31m[bus] {kind} handler {name} raised:\x1b[0m\n"
          + traceback.format_exc(), file=sys.stderr)
