"""Dev harness and capture tool.

    python -m mud                          play, with MIP decoded to stderr
    python -m mud --log captures/run.bin   also record raw bytes for tests
    python -m mud --quiet                  plain client, no MIP chatter

On exit it prints a tally of every line code seen, which is the inventory of
what 3k.org actually speaks -- as opposed to what anyone wrote down.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import queue
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import events
from . import update
from . import NAME, SLUG, __version__
from .capture import CaptureWriter
from .store import Store
from . import commands
from .botstore import RouteStore
from .profile import Characters, activate
from .rules import RuleStore
from .scripts import ScriptHost
from .web import WebServer
from .window import open_window

from .session import DEFAULT_HOST, DEFAULT_PORT, Session

DIM, CYAN, YELLOW, RED, GREEN, RESET = (
    "\x1b[2m", "\x1b[36m", "\x1b[33m", "\x1b[31m", "\x1b[32m", "\x1b[0m",
)


def colour_works() -> bool:
    """Can this console show an escape code, rather than print it?

    Windows consoles do not interpret them unless asked, and the asking is a
    Win32 call.  Without it every line the client prints about itself arrives
    with a literal "<-[2m" in front of it, which is how it looked the first
    time this ran on Windows.

    Redirected output is a separate question with the same answer: a log file
    full of escape codes is a log file nobody can read.
    """
    if not sys.stderr.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ok = False
        for stream in (-11, -12):                  # stdout, stderr
            handle = kernel32.GetStdHandle(stream)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            if kernel32.SetConsoleMode(
                    handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                ok = True
        return ok
    except Exception:
        # An old console, or no console at all.  Plain text always works.
        return False


def plain() -> None:
    """Say everything without colour, because colour would be noise."""
    global DIM, CYAN, YELLOW, RED, GREEN, RESET
    DIM = CYAN = YELLOW = RED = GREEN = RESET = ""


def home() -> Path:
    """Where this client keeps its things.

    Everything used to be relative to the working directory, which is fine
    while the only way to run it is `python3 -m mud` from the checkout and
    wrong the moment it is installed: a command you can type anywhere would
    otherwise scatter a map, a profile directory and a pile of captures into
    whatever directory you happened to be standing in.

    An existing `map.sqlite` beside you wins, so a checkout that already has
    one keeps working exactly as it did.  Otherwise $THREEK_HOME, else the
    usual place for a user's own data.
    """
    if Path("map.sqlite").exists():
        return Path(".")
    said = os.environ.get("DANK_HOME") or os.environ.get("THREEK_HOME")
    if said:
        return Path(said).expanduser()
    if sys.platform == "win32":
        # Never beside the program.  An installer puts that in Program Files,
        # which the user it installed for cannot write to -- and the map, the
        # profiles and the captures are all things the client writes.
        base = Path(os.environ.get("LOCALAPPDATA") or "~/AppData/Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or "~/.local/share")
    base = base.expanduser()
    mine = base / SLUG
    # An installation that predates the name keeps its map: renaming the
    # application is not a reason for anybody to lose fifty thousand rooms.
    was = base / "3k"
    if not mine.exists() and (was / "map.sqlite").exists():
        return was
    return mine


def build_parser() -> argparse.ArgumentParser:
    here = home()
    p = argparse.ArgumentParser(prog=SLUG,
                                description=NAME)
    p.add_argument("--version", action="version",
                   version=f"{NAME} {__version__}")
    p.add_argument("host", nargs="?", default=DEFAULT_HOST)
    p.add_argument("port", nargs="?", type=int, default=DEFAULT_PORT)
    p.add_argument("--log", metavar="STEM",
                   help=f"capture stem (default: {here / 'captures'}/<timestamp>)")
    p.add_argument("--no-log", action="store_true", help="do not record this session")
    p.add_argument("--sec", type=int, help="fixed security code (default: random)")
    p.add_argument("--quiet", action="store_true", help="don't echo MIP to stderr")
    p.add_argument("--web", nargs="?", type=int, const=-1, metavar="PORT",
                   help="serve the browser UI (default: 8080, or the next free "
                        "one; 0 = let the machine choose)")
    p.add_argument("--apm", type=int, default=100, metavar="N",
                   help="actions-per-minute ceiling 3k.org watches for "
                        "(default 100; movement does not count)")
    p.add_argument("--map", default=str(here / "map.sqlite"), metavar="FILE",
                   help="map and log database (default: %(default)s)")
    p.add_argument("--no-map", action="store_true",
                   help="do not map or log this session")
    p.add_argument("--scripts", default=str(here / "scripts"), metavar="DIR",
                   help="directory of user scripts, reloaded as you save "
                        "them (default: %(default)s)")
    p.add_argument("--profiles", default=str(here / "profiles"), metavar="DIR",
                   help="where each character's own settings live "
                        "(default: %(default)s)")
    p.add_argument("--character", metavar="NAME",
                   help="play this one straight away, skipping the login "
                        "screen; its password is sent if you asked us to keep "
                        "one")
    p.add_argument("--no-profiles", action="store_true",
                   help="one shared set of rules for every character")
    p.add_argument("--no-scripts", action="store_true", help="don't load scripts")
    p.add_argument("--web-host", default="127.0.0.1", metavar="ADDR",
                   help="bind address for the UI. Defaults to loopback only; "
                        "use 0.0.0.0 to reach it from another machine on the "
                        "LAN instead of tunnelling (no auth -- trusted networks only)")
    p.add_argument("--no-bootstrap", action="store_true",
                   help="on a first run, do not fetch the map and bots from "
                        "3kdb")
    p.add_argument("--app", action="store_true",
                   help="run as a window of its own, and stop when it closes")
    p.add_argument("--open", dest="open_ui", action="store_true",
                   help="open the UI in the ordinary browser instead")
    p.add_argument("--no-reconnect", action="store_true",
                   help="quit when the MUD drops us, instead of going back")
    p.add_argument("--no-jumpstart", action="store_true",
                   help="do not announce the 3klient handshake once you are "
                        "logged in (MIP then only starts if you ask, with /js)")
    return p


async def amain(args: argparse.Namespace) -> int:
    # Capture by default: forgetting to pass --log is the failure mode, and
    # a session you can't replay is a session you have to play again.
    raw_log = None
    if not args.no_log:
        stem = args.log or str(
            home() / "captures" / f"{datetime.now():%Y%m%d-%H%M%S}")
        raw_log = CaptureWriter(stem)
    store = None if args.no_map else Store(args.map)
    chars = None if args.no_profiles else Characters(args.profiles, args.scripts)
    session = Session(
        args.host,
        args.port,
        sec_code=args.sec,
        jumpstart=not args.no_jumpstart,
        raw_log=raw_log,
        store=store,
    )

    session.apm.limit = args.apm
    session.apm.soft = max(1, int(args.apm * 0.8))

    if args.web is None:
        out = sys.stdout.buffer

        @session.on_text.append
        def _(data: bytes) -> None:
            out.write(data)
            out.flush()

    if not args.quiet:
        @session.on_message.append
        def _(msg) -> None:
            data = msg.data if len(msg.data) <= 110 else msg.data[:107] + "..."
            print(f"{DIM}[{CYAN}{msg.code}{DIM}]{RESET} {data}", file=sys.stderr)

        @session.world.on_change
        def _(name: str, new, old) -> None:
            if name in ("hp", "sp", "enemy", "enemy_pct"):
                print(f"{DIM}  {name}: {old} -> {YELLOW}{new}{RESET}", file=sys.stderr)

    session.reconnect = not args.no_reconnect

    try:
        await session.connect()
    except OSError as exc:
        print(f"{RED}cannot connect to {args.host}:{args.port}: {exc}{RESET}",
              file=sys.stderr)
        return 1

    where = f"  logging to {raw_log.bin_path}" if raw_log else "  (not logging)"
    print(f"{DIM}connected {args.host}:{args.port}  sec_code={session.sec_code}"
          f"{where}  (/js forces the handshake){RESET}", file=sys.stderr)

    def _note(text: str) -> None:
        print(f"{YELLOW}{text}{RESET}", file=sys.stderr)

    # Say so.  A client quietly retrying looks exactly like a client that has
    # given up, and the difference matters when you are watching a reboot.
    session.bus.on(events.DISCONNECTED, lambda: _note("the MUD dropped us"))
    session.bus.on(events.RETRYING,
                   lambda wait: _note(f"reconnecting in {wait:.0f}s "
                                      f"(attempt {session.attempts})"))

    @session.bus.on(events.CONNECTED)
    def _() -> None:
        if session.connections > 1:
            print(f"{GREEN}  back on {args.host}:{args.port}{RESET}",
                  file=sys.stderr)

    async def keyboard() -> None:
        # A daemon thread can be abandoned at exit; an executor worker cannot,
        # and blocking on readline() would otherwise stall shutdown for 300s.
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            for raw in sys.stdin:
                lines.put(raw)
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()

        while True:
            line = await asyncio.to_thread(lines.get)
            if line is None:
                return
            line = line.rstrip("\n")
            if line.startswith("/"):
                commands.handle(line, session, host, _note)
            elif not (host and host.input(line)):
                session.queue.now(line)

    host = None
    if not args.no_scripts:
        host = ScriptHost(session, args.scripts)
        host.rules = RuleStore(host, Path(args.scripts) / "rules.json")
        host.routes = RouteStore(host, Path(args.scripts) / "routes.json")
        host.routes.load()
        host.rules.load()
        host.load_all()
        host.rules.register()
        host.start()
        loaded = sorted(host.registries)
        print(f"{DIM}  scripts: {', '.join(loaded) if loaded else 'none'} "
              f"({args.scripts}, hot-reloaded){RESET}", file=sys.stderr)

    # After the rules are loaded, because choosing a character replaces them.
    if chars is not None and args.character:
        char = chars.get(args.character)
        if char is None:
            print(f"{RED}no character called {args.character}; "
                  f"{'known: ' + ', '.join(c.name for c in chars.all) if chars.all else 'none saved yet'}"
                  f"{RESET}", file=sys.stderr)
            return 1
        activate(char, chars, session, host)
        session.login.begin(char.name, char.password)
        print(f"{DIM}  playing {char.name} "
              f"({chars.dir(char.name)}/){RESET}", file=sys.stderr)

    web = None
    if args.web is not None:
        # -1 is "you decide": the flag was given with no number, so 8080 if
        # it is free and the next one along if it is not.  A number that was
        # actually typed is honoured exactly, and fails if it cannot be.
        asked, spare = (8080, 20) if args.web == -1 else (args.web, 0)
        web = WebServer(session, host=args.web_host, port=asked,
                        scripts=host, characters=chars)
        try:
            port = await web.start(spare)
        except OSError as exc:
            print(f"{RED}cannot serve the UI on port {asked}: {exc}{RESET}\n"
                  f"{DIM}  something else is using it -- try --web 0 to let "
                  f"the machine choose{RESET}", file=sys.stderr)
            await session.aclose()
            return 1
        if port != asked and asked:
            print(f"{DIM}  port {asked} was taken; using {port}{RESET}",
                  file=sys.stderr)
        if args.web_host in ("127.0.0.1", "localhost"):
            print(f"{GREEN}  UI on http://127.0.0.1:{port}{RESET}"
                  f"{DIM}  (over ssh: -L {port}:localhost:{port}){RESET}",
                  file=sys.stderr)
        else:
            import socket as _s
            ip = _s.gethostbyname(_s.gethostname())
            print(f"{GREEN}  UI on http://{ip}:{port}{RESET}"
                  f"{YELLOW}  (bound to {args.web_host} -- unauthenticated){RESET}",
                  file=sys.stderr)

    window = None
    if web is not None and (args.app or args.open_ui):
        # Somebody who double-clicked an icon has no terminal to read a URL
        # out of.  Failing to show them one is not a reason not to start.
        where = f"http://127.0.0.1:{port}/"
        if args.app:
            window = await open_window(where, home() / "window", _note)
        if window is None:
            import webbrowser
            try:
                webbrowser.open(where)
            except Exception as exc:
                _note(f"could not open a browser: {exc}")

    async def first_run() -> None:
        """Fetch the world, once, on a client that has never had one.

        Somebody who has just installed this should not have to be told that
        the first thing to do is go and find fifty thousand rooms.  It happens
        in the background: the client is usable while it runs, and the login
        screen is the thing they should be looking at anyway.
        """
        _note("first run -- fetching the map and bot library from 3kdb "
              "(about 10MB, once)")
        try:
            got = await asyncio.to_thread(
                update.on_a_thread, args.map,
                str(Path(args.scripts) / "routes.json"), None, _note)
        except Exception as exc:
            _note(f"could not fetch it: {type(exc).__name__}: {exc}")
            _note("the client works without it; Options -> Updates will retry")
            return
        if got.get("error"):
            _note(f"could not fetch it: {got['error']}")
            _note("the client works without it; Options -> Updates will retry")
            return
        did = got.get("did", {})
        rooms = (did.get("map") or {}).get("rooms", 0)
        routes = (did.get("bots") or {}).get("added", 0)
        marks = (did.get("speedruns") or {}).get("added", 0)
        _note(f"ready: {rooms} rooms, {marks} named destinations, "
              f"{routes} routes")
        # The store and the route list were written by another thread's
        # connection; this side is holding what it read before.
        if host is not None and getattr(host, "routes", None) is not None:
            host.routes.load()
        if web is not None:
            web.refresh()

    if store is not None and not args.no_bootstrap and update.never_run(store):
        asyncio.ensure_future(first_run())

    kb = asyncio.create_task(keyboard())
    try:
        # Returns when the MUD drops us -- and, unless --no-reconnect, not
        # until it has stopped answering the door as well.
        playing = asyncio.ensure_future(session.stay())
        if window is None:
            await playing
        else:
            # Closing the window is how you quit an application.  Whichever
            # ends first ends the other: the shutdown below then flushes the
            # log and marks the session finished, exactly as Disconnect does.
            shut = asyncio.ensure_future(window.wait())
            await asyncio.wait([playing, shut],
                               return_when=asyncio.FIRST_COMPLETED)
            if shut.done():
                # Closing the window is Disconnect, pressed a different way:
                # the log and the map go to disk, the bots stop, the session
                # row is marked finished and the socket closes.  No `quit` is
                # sent -- closing the connection and logging the character out
                # are different acts, and only one of them was asked for.
                _note("window closed -- saving")
                session.hangup()
            for task in (playing, shut):
                task.cancel()
            await asyncio.gather(playing, shut, return_exceptions=True)
            if window.returncode is None:
                window.terminate()
    except asyncio.CancelledError:
        pass
    finally:
        kb.cancel()
        # let the cancellation actually land before the loop goes away
        await asyncio.gather(kb, return_exceptions=True)
        if host is not None:
            host.stop()
        if web is not None:
            await web.stop()
        await session.aclose()
        if raw_log:
            raw_log.close()
        report(session)
    return 0


def report(session: Session) -> None:
    print(f"\n{DIM}--- codes seen ---{RESET}", file=sys.stderr)
    if not session.codes_seen:
        print("  (none -- did the handshake fire? try /js after logging in)",
              file=sys.stderr)
    for code, n in session.codes_seen.most_common():
        print(f"  {code}  {n:>6}", file=sys.stderr)
    if session.world.unknown_codes:
        print(f"{YELLOW}  undocumented: "
              f"{dict(session.world.unknown_codes)}{RESET}", file=sys.stderr)
    if session.mismatched:
        print(f"  ({session.mismatched} lines with a foreign security code)",
              file=sys.stderr)


def main() -> int:
    if not colour_works():
        plain()
    args = build_parser().parse_args()
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
