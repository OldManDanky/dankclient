"""Static file + WebSocket server, stdlib only.

The project has no third-party dependencies and it is worth keeping that way:
a fresh checkout runs on a bare Python on any OS with nothing to install.
RFC 6455 is small enough that implementing the server half is cheaper than
taking a dependency for it.

The browser is a renderer, nothing more.  Python owns the socket, the MIP
scanner, world state and (later) bots; the UI receives typed JSON events and
draws them.  That keeps the boundary clean enough to swap the shell -- browser
tab now, pywebview later -- without touching anything below it.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import traceback
import hashlib
import json
import math
import mimetypes
import struct
import time
import urllib.parse
from importlib import resources
from pathlib import Path

from . import events

def log(*parts: object) -> None:
    print("\x1b[2m[web]\x1b[0m", *parts, file=sys.stderr, flush=True)


#: RFC 6455 s4.2.2, verbatim.  Get a character wrong and the handshake
#: still looks well formed, but every browser computes a different accept
#: value and hangs up without sending a byte.  Pinned by a test against
#: the RFC's own vector -- never against a value this module computes.
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The browser code, read through importlib rather than off the filesystem.
#: A zipapp has no filesystem: `Path(__file__).parent / "ui"` is a path inside
#: an archive, and read_bytes() on it fails.  importlib.resources reads either.
UI_PACKAGE = (__package__ or "mud", "ui")


def ui_file(name: str) -> bytes:
    """One file of the browser UI, by its URL path.

    The traversal check is ours to do here.  Path.resolve() and relative_to()
    used to do it, and both are filesystem operations that a zipapp does not
    have -- so the name is taken apart and any part that could climb out of
    the directory is refused before anything is opened.
    """
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise FileNotFoundError(name)
    where = resources.files(UI_PACKAGE[0]) / UI_PACKAGE[1]
    for part in parts:
        where = where / part
    return where.read_bytes()

#: Lines of this session put back into a terminal that has just opened.  Enough
#: to cover a fight and the walk to it; not so many that a refresh spends a
#: second drawing history nobody is going to scroll back through.
SCROLLBACK = 400

OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x1, 0x2, 0x8, 0x9, 0xA


def ours(origin: str) -> bool:
    """Is this websocket coming from our own page, or from somebody else's?

    WebSockets are not subject to the same-origin policy: any page a player
    visits while playing can open one to 127.0.0.1 and drive this client --
    send commands as them, write triggers, read the log.  Binding to loopback
    does not help, because the connection comes from their own browser, and
    the port and the message format are both public.

    Browsers always send Origin on the handshake.  Anything without one is not
    a browser -- a test, a script, a tool on the same machine -- and something
    running locally can already do anything, so those are let through.

    The port is deliberately not checked: an ssh tunnel forwards to whatever
    local port it likes, and the page is then served from that one.
    """
    if not origin:
        return True
    host = urllib.parse.urlsplit(origin).hostname
    return host in ("127.0.0.1", "localhost", "::1")


def _accept_key(key: str) -> str:
    digest = hashlib.sha1(key.encode() + WS_GUID).digest()
    return base64.b64encode(digest).decode()


def _frame(payload: bytes, opcode: int = OP_TEXT) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


async def _read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    header = await reader.readexactly(2)
    opcode = header[0] & 0x0F
    masked = header[1] & 0x80
    length = header[1] & 0x7F

    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]

    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


class WebServer:
    #: set on real instances; declared here so a partially
    #: constructed server still answers sensibly
    scripts = None
    characters = None
    _live_routes: frozenset = frozenset()
    #: Where the browser's copy of the map is centred, so an unchanged view is
    #: not rebuilt and resent.  Cleared when the graph is edited.
    _map_centre: int | None = None

    def __init__(self, session, host: str = "127.0.0.1", port: int = 0,
                 scripts=None, characters=None) -> None:
        self.session = session
        self.scripts = scripts        # ScriptHost, for alias interception
        self.characters = characters  # Characters, for the login screen
        self.host, self.port = host, port      # bind address

        self._clients: set[asyncio.StreamWriter] = set()
        self._dirty = True
        self._live_routes = frozenset()
        self._map_centre = None
        self._server: asyncio.base_events.Server | None = None
        #: What the latest release is, once we have asked.  Asked once, in the
        #: background: nobody wants their MUD client stopping to talk to
        #: GitHub, and the answer does not change while they play.
        self._release: dict = {}

    # --- lifecycle ----------------------------------------------------------

    async def start(self, spare: int = 0) -> int:
        """Bind, moving off a port somebody else already has.

        A packaged client is started by double-clicking, and "only one usage of
        each socket address is normally permitted" is not a thing to hand a
        player as a traceback -- particularly when the fix is a different
        number and nobody cares which.  A port that was asked for by name is
        different: that one is refused loudly, because the caller meant it.
        """
        want = self.port
        for step in range(max(0, spare) + 1):
            try:
                self._server = await asyncio.start_server(
                    self._handle, self.host, want + step)
                break
            except OSError:
                if step == spare:
                    if not spare:
                        raise
                    # Every one of them taken: let the machine choose.
                    self._server = await asyncio.start_server(
                        self._handle, self.host, 0)
        self.port = self._server.sockets[0].getsockname()[1]
        self._wire_session()
        asyncio.create_task(self._pump())
        asyncio.create_task(self._ask_about_releases())
        return self.port

    async def _ask_about_releases(self) -> None:
        """Find out whether there is a newer client, once, quietly.

        A failure is an empty answer, not a message: somebody playing offline
        does not need to be told that GitHub was unreachable.
        """
        from . import update

        try:
            self._release = await asyncio.to_thread(update.newer_release)
        except Exception:
            log("release check failed:\n" + traceback.format_exc())
            self._release = {"error": "could not ask"}
        self._dirty = True

    async def stop(self) -> None:
        for w in list(self._clients):
            _shut(w)
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except (RuntimeError, OSError):
                pass

    def _wire_session(self) -> None:
        s = self.session
        bus = s.bus

        @bus.on(events.TEXT)
        def _(data: bytes) -> None:
            self.push({"t": "text", "d": data.decode(s.encoding, "replace")})

        @bus.on(events.STATE)
        def _(name, new, old) -> None:
            self._dirty = True

        @bus.on(events.ROOM)
        def _(room) -> None:
            self._dirty = True

        for kind in (events.TELL, events.CHAT):
            bus.on(kind, lambda obj, k=kind: self.push({"t": k, "d": _asdict(obj)}))

    def _routes_changed(self) -> bool:
        """Has any route started, stopped or moved since we last looked?

        A route that reaches the end of its path stops itself, and the panel
        would otherwise go on claiming it was walking until somebody clicked
        something.  Progress counts as a change too: the sidebar says which
        step of how many, and a step counter that only moves when a route
        starts or stops is not a step counter.
        """
        store = getattr(self.scripts, "routes", None) if self.scripts else None
        if store is None:
            return False
        live = frozenset((b.name, b.steps, b.kills, b.note)
                         for b in self.scripts.bots.running)
        if live == self._live_routes:
            return False
        self._live_routes = live
        return True

    async def _pump(self) -> None:
        """Coalesce state pushes.  The round is 2000ms; 100ms is plenty."""
        while True:
            await asyncio.sleep(0.1)
            # While a countdown is running it is the only thing moving, and
            # nothing else will mark the state stale -- the MUD has stopped
            # talking, which is the whole problem.  Parked is different:
            # nothing is counting, and pushing anyway rebuilt the panel ten
            # times a second, which destroyed the button under the cursor
            # between the press and the release.
            s = self.session
            if not getattr(s, "connected", True) and getattr(s, "wanted", True):
                self._dirty = True
            if self._clients and self._routes_changed():
                self.push({"t": "routes", "op": "list",
                           "routes": self.scripts.routes.status()})
            if self._dirty and self._clients:
                self._dirty = False
                try:
                    self.push(self.snapshot())
                except Exception:
                    log("snapshot failed:\n" + traceback.format_exc())

    # --- outbound -----------------------------------------------------------

    def push(self, obj: dict) -> None:
        if not self._clients:
            return
        data = _frame(json.dumps(obj).encode())
        for w in list(self._clients):
            try:
                w.write(data)
            except (ConnectionError, OSError):
                self._clients.discard(w)

    def snapshot(self) -> dict:
        w = self.session.world
        p = w.player
        return {
            "t": "state",
            "player": {
                "hp": p.hp, "max_hp": p.max_hp, "hp_pct": p.hp_pct,
                "sp": p.sp, "max_sp": p.max_sp, "sp_pct": p.sp_pct,
                "gp1": p.gp1, "max_gp1": p.max_gp1,
                "gp2": p.gp2, "max_gp2": p.max_gp2,
                "enemy": p.enemy, "enemy_pct": p.enemy_pct,
                "round": getattr(p, "round", None),
                "gline": {
                    k: {"value": f.value, "colour": f.colour, "status": f.status}
                    for k, f in p.gline.items()
                },
            },
            "enemy_label": w.enemy_label,
            "labels": dict(w.labels),
            "messages": list(w.messages)[-80:],
            "room": {
                "short": w.room.short,
                "exits": w.room.exits,
                "contents": [_asdict(o) for o in w.room.contents],
                "scenery": [_asdict(o) for o in w.room.scenery],
            },
            "map": self._map_state(),
            "quiet": self.session.mip_quiet(),
            "apm": {
                "rate": self.session.apm.rate(),
                "soft": self.session.apm.soft,
                "limit": self.session.apm.limit,
                "queued": len(self.session.queue),
            },
            "mip": {
                "seen": self.session.mip_seen,
                "sec": self.session.sec_code,
                "codes": sum(self.session.codes_seen.values()),
            },
            "chrome": {
                "uptime": w.uptime, "reboot": w.reboot,
                "mudlag": w.mudlag, "editing": w.editing,
                "caption": w.caption,
            },
            "who": self._who(),
            "link": self._link(),
            "where": self._where(),
            # Absent until it has been asked, which is also what a
            # half-built server in a test looks like.
            "release": getattr(self, "_release", {}),
        }

    def _where(self) -> dict:
        """What this client is and where it keeps things.

        Installed, it says none of this: it lands somewhere without announcing
        it, and afterwards there is a Start Menu entry and no way to find out
        what it did.  "Where is my map" is a question asked more than once.
        """
        from . import NAME, __version__
        from .paths import home, program

        store = getattr(self.session, "store", None)
        return {
            "name": NAME,
            "version": __version__,
            "program": str(program()),
            "data": str(home().resolve()),
            "map": str(getattr(store, "path", "") or "(not mapping)"),
            "profiles": (str(self.characters.root.resolve())
                         if self.characters is not None else ""),
            "scripts": (str(Path(self.scripts.dir).resolve())
                        if getattr(self.scripts, "dir", None) else ""),
            "log": str((home() / "client.log").resolve()),
            "captures": str((home() / "captures").resolve()),
        }

    def _scrollback(self) -> dict | None:
        """The tail of this session's log, for a terminal that has just opened.

        A refresh used to empty it -- and a refresh is what you do after every
        change to the client, so the answer to "what just happened" was gone
        exactly when you wanted it.  It comes back from the log, which means it
        comes back without colour: the log stores lines ANSI-stripped, because
        nobody searches for an escape sequence.  Grey and ruled off, then --
        what happened, as against what is happening.
        """
        book = getattr(self.session, "logbook", None)
        if book is None:
            return None
        lines = book.tail(SCROLLBACK)
        return {"t": "back", "lines": lines} if lines else None

    def _link(self) -> dict:
        """How the connection is doing.

        Retrying in silence looks exactly like having given up, and the screen
        is the only place most of this is visible: the player is looking at a
        terminal that has simply stopped saying anything.
        """
        s = self.session
        left = s.retry_at - time.monotonic() if s.retry_at else 0.0
        return {
            "up": s.connected,
            "attempts": s.attempts,
            # Rounded up, so a countdown never sits on 0 for a whole second.
            "in": max(0, math.ceil(left)) if left > 0 else 0,
            # Whether it is coming back by itself.  A hang-up we asked for and
            # a link death look identical on screen otherwise, and only one of
            # them is waiting for you to do something about it.
            "reconnect": s.reconnect and getattr(s, "wanted", True),
        }

    def _who(self) -> dict:
        """Who is playing, and whether anything is waiting to be told."""
        char = getattr(self.session, "character", None)
        login = getattr(self.session, "login", None)
        asking = bool(login is not None and login.waiting)
        # Hung up on purpose: there is no MUD to ask the question, but picking
        # a character is still the answer -- it is what connects and plays.
        offline = bool(not getattr(self.session, "connected", True)
                       and not getattr(self.session, "wanted", True))
        return {
            "offline": offline,
            "character": char.name if char is not None else None,
            "known": self.characters.public() if self.characters else [],
            # The screen offers to log you in only while there is a prompt
            # waiting for it.  An hour into playing, picking a name should
            # load that character's rules, not type their name into the game.
            "asking": asking,
            # Shown by itself only before anyone has said who is playing.
            # Somebody who types their own name past it is already in, so the
            # screen gets out of the way rather than sitting over the game.
            "needed": bool(self.characters is not None and (
                offline
                or (char is None
                    and not self.session.mip_seen
                    and not (login is not None and login.done)))),
        }

    # --- the login screen ---------------------------------------------------

    def _login_op(self, msg: dict) -> None:
        from .profile import Character, activate

        chars = self.characters
        if chars is None:
            self._reply_login("no character list on this client")
            return
        op = msg.get("op")

        if op == "list":
            self._dirty = True
            return

        if op == "save":
            raw = msg.get("character") or {}
            name = str(raw.get("name", "")).strip()
            if not name:
                self._reply_login("a character needs a name")
                return
            keep = bool(raw.get("remember"))
            chars.put(Character(
                name=name,
                host=str(raw.get("host") or self.session.host),
                port=int(raw.get("port") or self.session.port),
                # An empty password means "leave what is there"; put() knows.
                password=str(raw.get("password") or "") if keep else "",
                note=str(raw.get("note") or ""),
            ))
            if not keep:
                # Asked to forget it, so forget it rather than leaving the old
                # one in place because the box came back empty.
                held = chars.get(name)
                if held is not None and held.password:
                    held.password = ""
                    chars.save()
            self._dirty = True
            return

        if op == "forget":
            chars.forget(str(msg.get("name", "")))
            self._dirty = True
            return

        if op == "play":
            char = chars.get(str(msg.get("name", "")))
            if char is None:
                self._reply_login("no such character")
                return
            activate(char, chars, self.session, self.scripts)
            typed = str(msg.get("password") or "")
            if msg.get("remember") and typed:
                char.password = typed
                chars.save()
            session = self.session
            login = getattr(session, "login", None)
            if not session.connected:
                # Chosen after a hang-up: this is who to come back as.  The
                # credentials go in first, because connecting resets the login.
                session.login_as(char.name, typed or char.password)
                session.resume()
            elif login is not None and login.waiting:
                session.login_as(char.name, typed or char.password)
            self._dirty = True
            return

        if op == "skip":
            login = getattr(self.session, "login", None)
            if login is not None:
                login.cancel()
            self._dirty = True
            return

    # --- 3kdb ---------------------------------------------------------------

    async def _update_op(self, msg: dict) -> None:
        from . import update

        op = msg.get("op")
        store = getattr(self.session, "store", None)
        if store is None:
            self.push({"t": "update", "op": "state",
                       "error": "this client is running without a map"})
            return

        if op == "check":
            # The settings are read here, on the loop's thread, because a
            # sqlite3 connection belongs to the thread that made it -- and this
            # failing inside a task is silent, which is how it went unnoticed
            # until an end-to-end run simply never answered.
            have = update.taken(store)
            try:
                got = await asyncio.to_thread(update.check, None, 20.0, have)
            except Exception as exc:
                log("update check failed:\n" + traceback.format_exc())
                got = {"error": f"{type(exc).__name__}: {exc}", "items": {}}
            self.push({"t": "update", "op": "state", **got})
            return

        if op == "client":
            await self._ask_about_releases()
            self.push({"t": "update", "op": "release", **self._release})
            return

        if op != "pull":
            return

        want = [k for k in (msg.get("want") or []) if k in update.WANTED]
        self.push({"t": "update", "op": "working",
                   "want": want or list(update.WANTED)})

        path = getattr(store, "path", None)
        routes = getattr(self.scripts, "routes", None)
        where = str(routes.path) if routes is not None else ""
        said: list[str] = []

        try:
            got = await asyncio.to_thread(
                update.on_a_thread, path, where, want or None, said.append)
        except Exception as exc:
            log("update failed:\n" + traceback.format_exc())
            got = {"error": f"{type(exc).__name__}: {exc}", "did": {}}

        # Whatever happens from here, the browser is told the work finished.
        # It sits on "working" until it hears, and an exception in a task is
        # silent -- which is how a panel ends up frozen with nothing in the log
        # to say why.
        try:
            # The worker wrote the file; this side is holding the old list.
            if routes is not None and not got.get("error"):
                routes.load()
                self.push({"t": "routes", "op": "list",
                           "routes": routes.status()})
            self._map_centre = None        # the drawn view may be stale now
            self._dirty = True
            for line in said:
                self.note(line)
        except Exception:
            log("after an update:\n" + traceback.format_exc())
        self.push({"t": "update", "op": "done", **got})

    def _reply_login(self, error: str) -> None:
        self.push({"t": "login", "op": "error", "error": error})

    # --- connections --------------------------------------------------------

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return

        lines = request.decode("latin-1").split("\r\n")
        try:
            method, path, _ = lines[0].split(" ", 2)
        except ValueError:
            writer.close()
            return
        headers = {}
        for line in lines[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                headers[k.lower()] = v

        upgrade = headers.get("upgrade", "").lower() == "websocket"
        log(f"{method} {path}" + ("  [websocket]" if upgrade else ""))
        if upgrade and not ours(headers.get("origin", "")):
            # Somebody else's page, in this player's browser, opening a socket
            # to this client.  Refuse before the handshake.
            log(f"refused a websocket from {headers.get('origin', '')!r}")
            writer.write(b"HTTP/1.1 403 Forbidden\r\n"
                         b"Content-Length: 0\r\nConnection: close\r\n\r\n")
            _shut(writer)
            return
        try:
            if upgrade:
                await self._websocket(reader, writer, headers)
            else:
                await self._static(writer, path)
        except (asyncio.CancelledError, GeneratorExit):
            raise                       # shutdown, not a failure
        except Exception:
            log("handler crashed:\n" + traceback.format_exc())
            _shut(writer)

    async def _static(self, writer: asyncio.StreamWriter, path: str) -> None:
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        try:
            body = ui_file(name)
            ctype = mimetypes.guess_type(name)[0] or "text/plain"
            status = "200 OK"
        except (ValueError, OSError, KeyError):
            body, ctype, status = b"not found", "text/plain", "404 Not Found"

        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        try:
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        _shut(writer)

    async def _websocket(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        headers: dict,
    ) -> None:
        key = headers.get("sec-websocket-key", "")
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + _accept_key(key).encode() + b"\r\n\r\n"
        )
        await writer.drain()

        self._clients.add(writer)
        # What was on screen before, before anything live.  The websocket is
        # ordered, so the terminal fills in the order it happened.
        back = self._scrollback()
        if back is not None:
            writer.write(_frame(json.dumps(back).encode()))
        writer.write(_frame(json.dumps(self.snapshot()).encode()))

        log(f"websocket open ({len(self._clients)} client(s))")
        why = "client closed"
        try:
            while True:
                frame = await _read_frame(reader)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == OP_CLOSE:
                    break
                if opcode == OP_PING:
                    writer.write(_frame(payload, OP_PONG))
                elif opcode == OP_TEXT:
                    self._on_client_message(payload)
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
            why = f"{type(exc).__name__}: {exc}"
        except (asyncio.CancelledError, GeneratorExit):
            self._clients.discard(writer)
            _shut(writer)
            raise
        except Exception:
            why = "crashed"
            log("websocket loop crashed:\n" + traceback.format_exc())
        finally:
            self._clients.discard(writer)
            _shut(writer)
            log(f"websocket closed -- {why}")

    def _on_client_message(self, payload: bytes) -> None:
        try:
            msg = json.loads(payload)
        except ValueError:
            return
        kind = msg.get("t")
        if kind == "rules":
            self._rules_op(msg)
            return
        if kind == "routes":
            self._routes_op(msg)
            return
        if kind == "login":
            self._login_op(msg)
            return
        if kind == "walk":
            self._walk(msg.get("to"))
            return
        if kind == "rename":
            store = getattr(self.session, "store", None)
            room = msg.get("room")
            if store is not None and isinstance(room, int):
                name = (msg.get("name") or "").strip()
                store.rename(room, name or None)
                self._map_centre = None       # the drawn view is now stale
                self._dirty = True
            return
        if kind == "help":
            from .commands import HELP

            self.push({"t": "help", "groups": [
                {"title": t, "blurb": b,
                 "rows": [{"verb": v, "what": d} for v, d in rows]}
                for t, b, rows in HELP]})
            return
        if kind == "update":
            # Network and a 25MB import: off the loop, or the browser and the
            # MUD both stop being served for four seconds.
            asyncio.create_task(self._update_op(msg))
            return
        if kind == "link":
            # Disconnect, and coming back from it.  Not a game command: the
            # session survives it, which is the point of the button.
            if msg.get("op") == "hangup":
                self.session.hangup()
                # When you last played is when you stopped, not when you
                # started -- it orders the login screen.
                char = getattr(self.session, "character", None)
                if self.characters is not None and char is not None:
                    self.characters.played(char.name)
                self.note("saved and disconnected")
            elif msg.get("op") == "resume":
                self.session.resume()
                self.note("reconnecting\u2026")
            self._dirty = True
            return
        if kind != "cmd":
            if kind == "jumpstart" and self._is_up():
                self.session.jumpstart()
            return

        text = msg.get("d", "")
        # "/" commands are for the client, not the MUD.  Without this, typing
        # /js in the browser sends it to 3K as a game command.
        if text.startswith("/"):
            self._client_command(text[1:].strip())
        elif not self._is_up():
            return
        elif not (self.scripts and self.scripts.input(text)):
            # A human is waiting on this one, so it bypasses the pacing queue.
            self.session.queue.now(text)

    def _is_up(self) -> bool:
        """Is there a socket to send down?  Says so when there is not.

        The terminal has simply stopped saying anything, so "why is nothing
        happening" is the actual question -- and a line typed into a dead
        connection should not come back as a traceback in the websocket loop.
        """
        if self.session.connected:
            return True
        wanted = getattr(self.session, "wanted", True)
        self.note("not connected -- " + (
            "press Reconnect" if not wanted
            else "reconnecting" if self.session.reconnect
            else "the MUD dropped us"))
        return False

    def _map_state(self) -> dict | None:
        """The map, but only when it has actually changed.

        Building the neighbourhood is a query per room, and the snapshot goes
        out several times a second.  What is drawn only changes when you move
        or when the graph is edited, so the rest of the time the browser is
        told to keep what it has.
        """
        mapper = getattr(self.session, "mapper", None)
        if mapper is None:
            return None
        state = mapper.status()
        if state["room"] is not None and state["room"] == self._map_centre:
            state["unchanged"] = True
            return state
        self._map_centre = state["room"]
        state.update(mapper.neighbourhood())
        return state

    def _walk(self, dest) -> None:
        """Walk to a room the map already knows a way to.

        One step at a time, each waiting for the room block the last one
        produced.  Sending them together looks like a speedwalk and is not:
        after the first step you are somewhere else, and the rest go out from
        a room they were never meant for.
        """
        mapper = getattr(self.session, "mapper", None)
        if mapper is None or not isinstance(dest, int):
            return
        route = mapper.route(dest)
        if route is None:
            self.note("no route from here" if mapper.here is not None
                      else "lost -- walk a room or two first")
            return
        self.session.travel(dest, "speedwalk")
        self.note(f"walking {len(route)} steps")

    def _routes_op(self, msg: dict) -> None:
        store = getattr(self.scripts, "routes", None) if self.scripts else None
        if store is None:
            self.push({"t": "routes", "op": "error",
                       "error": "scripting is disabled"})
            return

        op = msg.get("op")
        if op == "save":
            route, problem = store.upsert(msg.get("route") or {})
            if problem:
                self.push({"t": "routes", "op": "error", "error": problem})
                return
        elif op == "delete":
            store.delete(msg.get("id", ""))
        elif op == "start":
            problem = store.start(msg.get("id", ""))
            if problem:
                self.push({"t": "routes", "op": "error", "error": problem})
                return
        elif op == "stop":
            store.stop(msg.get("id", ""))
        elif op == "stop_all":
            self.scripts.bots.stop_all()
            self.session.queue.flush()

        self.push({"t": "routes", "op": "list", "routes": store.status()})

    def _rules_op(self, msg: dict) -> None:
        store = getattr(self.scripts, "rules", None) if self.scripts else None
        if store is None:
            self.push({"t": "rules", "op": "error",
                       "error": "scripting is disabled"})
            return

        op = msg.get("op")
        if op == "list":
            pass
        elif op == "save":
            rule, problem = store.upsert(msg.get("rule") or {})
            if problem:
                self.push({"t": "rules", "op": "error", "error": problem})
                return
        elif op == "delete":
            store.delete(msg.get("id", ""))
        elif op == "test":
            line = msg.get("line", "")
            # try it both ways: the same text may be a MUD line or something
            # you would type, and the panel holds both kinds of rule
            hits = [
                {"owner": t.owner, "pattern": t.pattern, "kind": kind,
                 "captured": {str(k): str(v) for k, v in (c or {}).items()}}
                for kind, which in (("trigger", self.scripts.triggers),
                                    ("alias", self.scripts.aliases))
                for t, c in which.fire(line)
            ]
            self.push({"t": "rules", "op": "tested", "line": line, "hits": hits})
            return
        elif op == "python":
            from .rules import Rule
            data = {k: v for k, v in (msg.get("rule") or {}).items()
                    if k in Rule.__dataclass_fields__}
            self.push({"t": "rules", "op": "python",
                       "code": Rule(**data).as_python()})
            return

        payload = store.listing()
        payload.update({"t": "rules", "op": "list"})
        self.push(payload)

    def _client_command(self, cmd: str) -> None:
        from . import commands
        commands.handle("/" + cmd, self.session, self.scripts, self.note)

    def refresh(self) -> None:
        """Something outside changed the map or the routes; redraw.

        The map panel only redraws when the room it is centred on changes, so
        a map that grew underneath it would otherwise stay as it was until the
        next step taken.
        """
        self._map_centre = None
        self._dirty = True
        routes = getattr(self.scripts, "routes", None)
        if routes is not None:
            try:
                self.push({"t": "routes", "op": "list",
                           "routes": routes.status()})
            except Exception:
                log("refreshing the routes:\n" + traceback.format_exc())

    def note(self, text: str) -> None:
        """A line from the client itself, not from the MUD.

        Every line ending has to be a carriage return as well: a terminal moves
        *down* on a newline and stays in the column it was in, so a multi-line
        note arrived as a staircase, each line starting where the last one
        ended.  /help is thirty-four lines of that.
        """
        body = "\r\n".join(str(text).replace("\r\n", "\n").split("\n"))
        self.push({"t": "text", "d": f"\r\n\x1b[33m[client] {body}\x1b[0m\r\n"})


def _shut(writer: asyncio.StreamWriter) -> None:
    """Close a writer without caring that the loop may already be gone."""
    try:
        writer.close()
    except (RuntimeError, OSError):
        pass


def _asdict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        return {f: _asdict(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, (list, tuple)):
        return [_asdict(o) for o in obj]
    return obj
