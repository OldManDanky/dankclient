"""Asyncio connection to the MUD.

Wires the pieces together::

    socket -> TelnetFilter -> Scanner -> World
                                  |
                                  `-> subscribers (UI, scripts, bots)
"""

from __future__ import annotations

import asyncio
import random
import re
import socket
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Callable

from . import codes, events
from . import SLUG, __version__
from .clock import Clock
from .events import Bus
from .lines import LineAssembler
from .logbook import Logbook
from .markup import Markup
from .mapper import Mapper
from . import patrol
from .outbound import APMMeter, SendQueue
from .login import Login
from .prefixes import Hidden, Prefixes
from .scanner import Message, Scanner, Text
from .state import World
from .telnet import TelnetFilter
from .gags import HOLD, LineGate
from .deadman import DEFAULT_MINUTES, Deadman
from .triggers import TriggerSet

DEFAULT_HOST = "3k.org"
DEFAULT_PORT = 3000

#: How long a room title waits for a DDD of its own before the room is made
#: from the title instead.  Measured over 1,127 titles in long mode: the DDD
#: follows in a median of 0.03s and 90% within 0.07s.  Every title that went
#: longer had no DDD of its own at all -- brief mode, mostly -- apart from
#: titles 3K had cut off mid-list, which never make a room anyway.
TITLE_WAIT = 0.25

#: How long a quiet connection is trusted, then how often and how many times
#: the other end is asked whether it is still there.  Dead in about a minute.
KEEPALIVE = (30, 10, 3)


def keep_alive(sock) -> bool:
    """Have the operating system notice a connection that died silently.

    A MUD can go quiet for minutes, so silence proves nothing -- and a link
    that dies without a word (a router rebooting, wifi changing, a laptop
    lid) leaves the read waiting for ever.  The client sits there saying
    "connected" while 3K has long since made you link-dead, and the reconnect
    that exists for exactly this never starts.  TCP keepalive asks the far end
    when the line has been quiet, and turns no answer into an error the read
    loop already treats as a drop.

    The system default is two hours, which is why it is tuned rather than just
    switched on.  Windows 10 and 11 take the same three options Linux does.
    """
    if sock is None:
        return False
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except (OSError, AttributeError):
        return False
    idle, every, tries = KEEPALIVE
    for name, value in (("TCP_KEEPIDLE", idle), ("TCP_KEEPINTVL", every),
                        ("TCP_KEEPCNT", tries)):
        option = getattr(socket, name, None)
        if option is None:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, option, value)
        except OSError:
            pass                        # an older Windows; on is still better
    return True


class Session:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        sec_code: int | None = None,
        version: str = "",
        jumpstart: bool = True,
        raw_log=None,
        store=None,
        prefixes_path: str = "scripts/prefixes.json",
        encoding: str = "latin-1",
    ) -> None:
        self.host, self.port = host, port
        self.encoding = encoding
        # The *client* invents this; the MUD stamps it on every MIP line so we
        # can ignore traffic meant for somebody else.
        self.sec_code = sec_code or random.randint(1, 99999)
        # What the MUD is told we are.  One version for the package, the
        # handshake and --version: three was two too many.
        self.version = version or f"{SLUG}{__version__}"
        #: announce ourselves once the login is behind us
        self.jumpstart_wanted = jumpstart
        self.raw_log = raw_log

        self.bus = Bus()
        self.clock = Clock()
        self.world = World(self.bus)
        self.apm = APMMeter()
        #: Long-running tasks that drive the character -- routes, hunts, a
        #: speedwalk.  On the session rather than the script host, because
        #: walking somewhere should work with scripting switched off, and
        #: because one place to see and stop them is the point.
        self.bots = patrol.Bots(self)
        self.store = store
        #: Grows the map as you walk.  Absent when there is no store to put it
        #: in, so the client runs unchanged with mapping switched off.
        self.mapper = Mapper(store) if store is not None else None
        #: Searchable history.  Shares the store with the map so a line can be
        #: asked "where was I standing".
        self.logbook = Logbook(store, self.mapper) if store is not None else None
        self.world.log_to = self.logbook
        #: Reads the fields 3K wraps its output in.  The room title arrives
        #: with every room and arrives at once, where BAD names fewer than
        #: half of them and does it on the tick.
        self.prefixes_path = prefixes_path
        self.prefixes = Prefixes(prefixes_path)
        self.markup = Markup.from_prefixes(self.prefixes)
        #: ...and takes them back out before anyone sees them.  They are
        #: scaffolding for the parser, and a player typing `look` should not
        #: have to read around it.
        self.hidden = Hidden((v for _, v in self.prefixes.pairs),
                             keep=(n for n, _ in self.prefixes.pairs))
        if self.mapper is not None:
            self.bus.on(events.ROOM, self._on_room)
        #: Pauses everything automated once nobody has typed for a while.
        #: Kept with the map, because it is the client enforcing it.
        minutes = DEFAULT_MINUTES
        if store is not None:
            try:
                minutes = float(store.setting("deadman:minutes",
                                              str(DEFAULT_MINUTES)))
            except (ValueError, TypeError):
                pass
        self.deadman = Deadman(minutes, on_change=self._deadman_changed)
        # Movement is exempt, and DDD tells us what counts as movement *here*,
        # so named exits like "omp" or "vortex" are free too.
        self.queue = SendQueue(self.send, self.clock, apm=self.apm,
                               held=lambda: self.deadman.tripped,
                               exits=lambda: self.world.room.exits,
                               # Exactly what `send` can do: anything queued
                               # while there is nothing to write to waits for
                               # a socket rather than raising at whoever put
                               # it there.
                               ready=lambda: self._writer is not None)
        self.codes_seen: Counter[str] = Counter()
        self.mismatched = 0
        self.jumpstarted = False
        self.mip_seen = False
        self._armed = False
        self._last_jumpstart = 0.0
        #: re-announce this often while armed but silent
        self.jumpstart_retry = 15.0

        #: Is the socket up?  Not the same question as "are we playing": a
        #: reconnect has the socket back long before the login is answered.
        self.connected = False
        #: Should we be connected at all?  False after a deliberate hang-up,
        #: which is a different thing from a drop: one is to be recovered
        #: from, the other is to be left alone until somebody asks.
        self.wanted = True
        #: Put the connection back when it drops *without* being asked to.  A
        #: link death is not a reason to lose the map, the rules, or the
        #: browser on the other end of the websocket -- they belong to the
        #: character, not to the socket.
        self.reconnect = True
        #: Attempts since the last connection we actually had, and when the
        #: next one is due (monotonic, 0.0 when none is pending).  Both are on
        #: screen while it is happening: a client retrying silently is one you
        #: cannot tell from a client that has given up.
        self.attempts = 0
        self.retry_at = 0.0
        #: Connections made since the client started.  More than one means the
        #: session has been through a link death and come back.
        self.connections = 0
        self.backoff_first = 2.0
        self.backoff_longest = 60.0
        #: A connect with no answer at all -- packets dropped rather than
        #: refused -- otherwise waits on the operating system, which is two
        #: minutes on Linux, and Disconnect cannot interrupt it meanwhile.
        self.connect_timeout = 20.0
        self._stopping = False
        #: Set to wake the loop out of a parked state -- somebody has asked
        #: for the connection back.
        self._asked = asyncio.Event()
        #: Who to answer the prompts as on the next connection, and with what.
        #: Held in memory for the life of the client and written nowhere: a
        #: link death should not leave you at the password prompt just because
        #: you chose not to save the password.
        self._credentials: tuple[str, str] | None = None

        self.on_text: list[Callable[[bytes], None]] = []
        self.on_message: list[Callable[[Message], None]] = []
        self.on_prompt: list[Callable[[], None]] = []

        #: Who is playing.  None until somebody says, which is the state the
        #: login screen exists to get out of.
        self.character = None
        #: The name typed at 3K's own name prompt, for somebody who logged in
        #: without the login screen.  The character, when chosen, wins.
        self.me = ""
        #: Answers the name and password prompts when a character is chosen.
        #: Given a lambda rather than the bound method, so it goes through
        #: whatever `send` is at the time -- a bound method captured here is
        #: one that ignores anything wrapped around it later.
        self.login = Login(lambda text, secret=False: self.send(text, secret))


        self._scanner = Scanner(encoding=encoding)
        self._telnet = TelnetFilter()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tail = ""
        self._lines = LineAssembler(encoding)
        #: Lines kept off the screen.  Filled by the rules and scripts that
        #: ask for it; the triggers and the log still see every line.
        self.gags = TriggerSet()
        self.gate = LineGate(self.is_gagged, encoding,
                             active=lambda: len(self.gags) > 0)
        self._release: asyncio.TimerHandle | None = None

        #: 3K's `brief` setting as it last reported it: {"brief": "on",
        #: "mapping": "yes"}, or None until it has said.  Read off its reply
        #: rather than remembered from what we sent, because the character's
        #: setting is the truth and it can be changed from anywhere.
        self.brief: dict | None = None
        self.bus.on(events.LINE, self._on_line)
        # Asked on the game's beat, so the deadman trips when the time is up
        # rather than at the next thing that happens to want to send.
        self.bus.on(events.TICK, lambda *_: self.deadman.tripped)
        #: The last marked room title still waiting to find out whether a DDD
        #: is coming for it: (when, exits, contents so far, scenery so far).
        self._titled: tuple | None = None
        self._title_timer: asyncio.TimerHandle | None = None

        # The two signals that expose the 2s server beat: N while fighting,
        # E while guild points regenerate.  Neither is always present.
        self.bus.on(events.STATE, self._on_state)

    #: "Your brief setting is currently: [on, mapping yes]"
    BRIEF = re.compile(r"brief setting is currently:\s*\[(on|off),\s*mapping\s+(yes|no)\]",
                       re.I)

    def _on_line(self, raw: str, plain: str) -> None:
        hit = self.BRIEF.search(plain)
        if hit:
            self.brief = {"brief": hit.group(1).lower(),
                          "mapping": hit.group(2).lower()}

    def _on_state(self, name: str, new, old) -> None:
        if name == "round":
            if new:
                self.clock.observe("round")
            self.bus.emit(events.ROUND, new)
        elif name == "enemy":
            self.bus.emit(events.ENEMY, new)
        elif name == "gp1" and old is not None:
            self.clock.observe("regen")
        elif name == "short" and new and self.mapper is not None:
            # BAD is a periodic sample of "what room am I in", so it names
            # wherever we are now -- not the block that just arrived, which it
            # usually trails.  It carries the exits too, but DDD is the
            # authority on those, so only the name is kept.
            self.mapper.name_here(codes.parse_bad(new)[0])

    # --- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        self._forget_the_connection()
        # A timeout is a TimeoutError, which is an OSError: to everything
        # above this, a connect that never answered is one that failed.
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            self.connect_timeout)
        keep_alive(self._writer.get_extra_info("socket"))
        self.connected = True
        self.connections += 1
        self.attempts = 0
        self.retry_at = 0.0
        self.clock.start(self.bus)
        self.queue.start()
        self.bus.emit(events.CONNECTED)

    async def run(self) -> None:
        """Read until the MUD stops talking to us."""
        assert self._reader is not None
        try:
            while True:
                chunk = await self._reader.read(4096)
                if not chunk:
                    break
                try:
                    self._consume(chunk)
                except Exception:
                    # Nothing the MUD sends should stop the client reading,
                    # because everything else hangs off this loop.  Ten
                    # thousand mutated chunks of real captures found nothing
                    # that does -- this is so that the next thing costs one
                    # chunk rather than the session.
                    print("[client] could not handle what the MUD sent:\n"
                          + traceback.format_exc(), file=sys.stderr)
        except (ConnectionError, OSError):
            # A connection reset is a disconnection.  It used to come out of
            # here as an exception and take the whole client with it, browser
            # and all, which is a lot to lose over a bad hop.
            pass
        self.connected = False
        self.bus.emit(events.DISCONNECTED)

    async def stay(self) -> None:
        """Hold the connection in whatever state was asked for.

        The read is the inner loop, so the client outlives the socket.  3K
        drops you for a reboot, for a bad hop, for nothing at all; the map, the
        rules, the log and the open browser are all still perfectly good when
        it does, and the only things that are not are the ones the socket
        owned.

        Three states, and the difference between the last two is the whole
        point: connected; dropped and trying to get back; and parked, which is
        what a hang-up we asked for leaves behind.  A client that reconnects
        two seconds after you press Disconnect is a client with a broken
        button, so a parked session sits here -- browser, map and log all still
        up -- until somebody asks for it back.
        """
        parked = False
        while not self._stopping:
            if self.connected:
                await self.run()          # returns when the MUD stops talking
                parked = False
                continue
            if not self.wanted:
                await self._asked.wait()
                self._asked.clear()
                parked = True
                continue
            # --no-reconnect, and every replay of a capture: the end of the
            # input is the end.  Asking for it back by hand still works.
            if self.connections and not self.reconnect and not parked:
                return
            got = await self._come_back(0.0 if parked else None)
            parked = False
            if not got:
                if self._stopping:
                    return
                continue                  # hung up while we were trying

    async def _come_back(self, wait: float | None = None) -> bool:
        """Try again until it works.  False if we were stopped or hung up on.

        No attempt limit: a reboot takes as long as it takes, and a client that
        gives up after five tries is one you find dead an hour later.  The wait
        is capped instead, so it keeps knocking without hammering.  A wait of
        zero is somebody pressing Reconnect, who should not be made to sit
        through a backoff they did not cause.
        """
        wait = self.backoff_first if wait is None else wait
        while not self._stopping:
            self.attempts += 1
            if wait:
                self.retry_at = time.monotonic() + wait
                self.bus.emit(events.RETRYING, wait)
                try:
                    await asyncio.sleep(wait)
                except asyncio.CancelledError:
                    return False
            if self._stopping or not self.wanted:
                return False
            try:
                await self.connect()
            except OSError:
                wait = self.backoff_first if not wait else min(
                    wait * 2, self.backoff_longest)
                continue
            self._log_back_in()
            return True
        return False

    def hangup(self) -> None:
        """Put the session away and close the connection, on purpose.

        Everything the client is holding goes to disk first: the log buffers a
        few seconds of history, and a few seconds is still history.  Then the
        socket goes and nothing brings it back -- a drop we asked for is not
        one to recover from.  The client itself stays up, so the map, the log
        and the open browser are all still there to come back to.
        """
        self.wanted = False
        # Say so now rather than when the read loop notices.  It is closing
        # the socket; claiming to be connected until something else works that
        # out leaves the screen a beat behind the truth, and leaves it wrong
        # for good if the loop is cancelled before it gets there.
        self.connected = False
        self.bots.stop_all()
        if self.logbook is not None:
            self.logbook.close()      # flush, and mark the session finished
        if self.store is not None:
            self.store.db.commit()
        if self._writer is not None:
            self._writer.close()
            # Forgotten, not just closed: sending down a hung-up connection
            # should be refused rather than written into a socket on its way
            # out, and the queue reads this to know to hold.
            self._writer = None
        self._asked.set()

    def resume(self) -> None:
        """Ask for the connection back, now rather than after a backoff."""
        self.wanted = True
        if self.logbook is not None:
            self.logbook.reopen()     # it did not finish after all
        self._asked.set()

    def login_as(self, name: str, password: str = "") -> None:
        """Play as this character: now if there is a connection, else on the
        next one.

        The login screen calls this for both, because they are the same act.
        Choosing a name at the prompt and choosing one after pressing
        Disconnect differ only in whether the socket exists yet, and that is
        not a difference the player should have to think about.
        """
        name = (name or "").strip()
        if not name:
            return
        self._credentials = (name, password)
        if self.connected:
            self.login.begin(name, password)

    def _log_back_in(self) -> None:
        """Answer the two questions again, if we know the answers.

        Not from the login, which clears the password the moment it has been
        typed -- from whoever was chosen last, falling back to the character's
        saved one.  With nobody chosen there is nothing to type, and the login
        screen asks.
        """
        name, password = self._credentials or ("", "")
        if not name:
            char = self.character
            if char is None or not getattr(char, "name", ""):
                return
            name, password = char.name, getattr(char, "password", "") or ""
        self.login.begin(name, password)

    def _forget_the_connection(self) -> None:
        """Drop everything the socket owned, and keep everything else.

        What does not survive a connection: half a MIP message, half a line,
        half a room description, a route walking somewhere, the belief that we
        know which room we are standing in, and the handshake -- MIP is
        something the MUD does for a connection, and the new one has never
        heard of us.  Everything else is the character's and stays.
        """
        self.connected = False
        self.clock.stop()
        self.queue.stop()
        self.bots.stop_all()
        if self._writer is not None:
            self._writer.close()          # already dead, usually; say so anyway
        self._reader = None
        self._writer = None
        self._scanner = Scanner(encoding=self.encoding)
        self._telnet = TelnetFilter()
        self._lines = LineAssembler(self.encoding)
        self._tail = ""
        self.gate.reset()               # half a line is the socket's too
        if self._release is not None:
            self._release.cancel()
            self._release = None
        self._titled = None
        if self._title_timer is not None:
            self._title_timer.cancel()
            self._title_timer = None
        # Rebuilds the markup reader and the marker filter, both of which hold
        # a fragment across reads, and picks up an edit to the file while it is
        # there.
        self.reload_prefixes()
        self.mip_seen = False
        self.jumpstarted = False
        self._armed = False
        self._last_jumpstart = 0.0
        self.login.reset()
        if self.mapper is not None:
            self.mapper.unsure()

    async def aclose(self) -> None:
        self._stopping = True
        self._asked.set()          # a parked loop is waiting on this
        self.clock.stop()
        self.queue.stop()
        if self.logbook is not None:
            self.logbook.close()      # a few seconds of history is still history
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    # --- inbound ------------------------------------------------------------

    def _consume(self, chunk: bytes) -> None:
        self._room_from_title()          # one that has waited long enough
        if self.raw_log is not None:
            self.raw_log.write(chunk)
            self.raw_log.flush()

        clean, reply, marks = self._telnet.feed(chunk)
        if reply and self._writer is not None:
            self._writer.write(reply)

        for event in self._scanner.feed(clean):
            if isinstance(event, Text):
                self._on_text(event.data)
            else:
                self._on_message(event)

        for mark in marks:
            if mark == "prompt":
                # Nothing more is coming, so a tail held back in case it grew
                # into a marker is just text.  Show it.
                held = self.hidden.flush()
                if held:
                    self._show(held)
                self._let_go()
                self.bus.emit(events.PROMPT)
                for fn in self.on_prompt:
                    fn()

    # --- the deadman ---------------------------------------------------------

    def _deadman_changed(self, tripped: bool) -> None:
        if tripped:
            self.queue.flush()            # nothing waiting goes out later
            minutes = self.deadman.minutes
            said = (f"deadman: {minutes:g} minute{'s' if minutes != 1 else ''} "
                    f"without you typing -- bots paused, and nothing automated "
                    f"will be sent until you type a command.")
        else:
            said = "deadman: you're back -- carrying on."
        self.bus.emit(events.TEXT,
                      f"\r\n\x1b[33m[client] {said}\x1b[0m\r\n".encode("latin-1"))
        self.bus.emit(events.STATE, "deadman", tripped, not tripped)

    # --- rooms that arrive as a title alone ---------------------------------

    def _title_arrived(self, exits) -> None:
        """A marked room title: wait a moment to see if a DDD comes with it."""
        # One still waiting has had no DDD -- another title came first, which
        # in long mode never happens -- so it was a room of its own.  Two
        # brief steps inside the wait used to lose the first of them.
        self._room_from_title(now=True)
        room = self.world.room
        self._titled = (time.time(), list(exits), len(room.contents),
                        len(room.scenery))
        if self._title_timer is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return                  # replaying: the next message decides
            self._title_timer = loop.call_later(TITLE_WAIT + 0.01,
                                                self._title_timeout)

    def _title_timeout(self) -> None:
        self._title_timer = None
        self._room_from_title()

    def _room_from_title(self, now: bool = False) -> None:
        """No DDD came for the last title: the room is the title's.

        Brief mode sends none with a step, so this is the only way the map
        hears about it.  In long mode the DDD always comes first and this
        does nothing.  `now` is for when it is already clear none is coming.
        """
        if self._titled is None:
            return
        at, exits, contents_from, scenery_from = self._titled
        if not now and time.time() - at < TITLE_WAIT:
            return
        self._titled = None
        self.world.titled_room(exits, at, contents_from, scenery_from)

    # --- the screen ---------------------------------------------------------

    def is_gagged(self, plain: str) -> bool:
        """Is this line one the player has asked not to see?"""
        return bool(self.gags.fire(plain))

    def _show(self, data: bytes) -> None:
        """Send text to the screen, through the gags."""
        out = self.gate.feed(data)
        if out:
            self.bus.emit(events.TEXT, out)
        if self.gate.pending and self._release is None:
            # An unfinished line: the rest of it, or a prompt with no end.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._let_go()            # nothing to wait with; show it now
                return
            self._release = loop.call_later(HOLD, self._let_go)

    def _let_go(self) -> None:
        """Show an unfinished line that has waited long enough for its end."""
        self._release = None
        out = self.gate.release()
        if out:
            self.bus.emit(events.TEXT, out)

    def reload_prefixes(self, path=None) -> None:
        """Pick up an edit to the settings file, or another character's."""
        if path is not None:
            self.prefixes_path = str(path)
            self.prefixes.path = Path(path)
        self.prefixes.load()
        self.markup = Markup.from_prefixes(self.prefixes)
        self.hidden = Hidden((v for _, v in self.prefixes.pairs),
                             keep=(n for n, _ in self.prefixes.pairs))

    def _on_text(self, data: bytes) -> None:
        self.login.feed(data.decode(self.encoding, "replace"))
        self._show(self.hidden.feed(data))
        for raw, plain in self._lines.feed(data):
            # The markup reader gets the markers; it is the one thing that
            # wants them.  Everything downstream of here sees the line the
            # player sees, so a trigger can be written against that.
            title = self.markup.feed(plain)
            if title and title.get("closed") and title.get("exits"):
                self._title_arrived(title["exits"])
            shown, was = self.hidden.line(plain), plain
            self.bus.emit(events.LINE, self.hidden.line(raw), shown)
            if self.logbook is not None and (shown.strip() or not was.strip()):
                # The stripped line, not the raw one: nobody searches for an
                # escape sequence, and the colours would swamp the index.
                self.logbook.add("recv", shown)
        for fn in self.on_text:
            fn(data)

        if self.mip_seen or not self.jumpstart_wanted:
            return

        # The handshake goes out once the login is behind us, and not one byte
        # before: announced at the name prompt, "3klient 40142~1.0" is simply
        # typed in as somebody's character name.
        #
        # This used to watch for a phrase in the login spam, the way Portal
        # does, and the phrase was "Welcome".  3K answers a reconnect with
        # "3Kingdoms welcomes you back from linkdeath", which does not contain
        # it -- so on the common path it never fired and the handshake had to
        # be sent by hand.  The login itself is the thing that actually
        # happened; watch that instead of guessing at wording.
        if self.login.inside:
            self._armed = True

        # The MUD can still be settling when we first ask, so keep announcing
        # until MIP actually starts flowing.
        if self._armed and time.monotonic() - self._last_jumpstart >= self.jumpstart_retry:
            self.jumpstart()

    def _on_message(self, msg: Message) -> None:
        self.codes_seen[msg.code] += 1
        self.mip_seen = True
        if int(msg.sec) != self.sec_code:
            self.mismatched += 1
            return
        if msg.code == "DDD" and self.world._last_code != "BAD":
            self._titled = None        # the title had a DDD of its own after all
        else:
            self._room_from_title()
        self.world.apply(msg.code, msg.data)
        self.bus.emit(events.MIP, msg)
        for fn in self.on_message:
            fn(msg)

    def follow(self, route, name: str = "speedwalk") -> bool:
        """Walk a route, a step at a time.  False if there was nothing to do."""
        if not route:
            return False
        api = patrol.make_api(self, self.bots, "client")
        self.bots.start(name, lambda: api["follow"](route, name), "client")
        return True

    def travel(self, dest: int, name: str = "speedwalk") -> bool:
        """Get to a room, routing around ways out that do not work."""
        if self.mapper is None:
            return False
        api = patrol.make_api(self, self.bots, "client")
        self.bots.start(name, lambda: api["travel"](dest, name), "client")
        return True

    def mip_quiet(self) -> list[str]:
        """Codes the MUD ought to be sending and is not.

        3K can be told to stop sending a code, and a character's own settings
        can stop one too: setting the look_* markers silenced HAA outright,
        which took the room's contents with it and left routes with nothing to
        attack.  Nothing announced that; it simply stopped.  So the codes that
        travel together are checked against each other.
        """
        missing = []
        if self.codes_seen.get("DDD", 0) >= 5:
            for code, why in (("HAA", "room contents"),
                              ("HAB", "room scenery")):
                if not self.codes_seen.get(code):
                    missing.append(f"{code} ({why})")
        return missing

    def _on_room(self, room) -> None:
        was = self.mapper.here
        # The MUD prints the room, then MIP says which room it was, so a
        # title read from the text belongs to the block that follows it.
        name, _desc = self.markup.take(room.exits)
        here = self.mapper.arrived(
            list(room.exits),
            [o.name for o in room.scenery],
            name=name or None,
            at=room.opened_at,
        )
        if (self.logbook is not None and here is not None and here != was
                and self.mapper.moved_at is not None):
            # The room's description reached us before MIP said which room it
            # was, so those lines are filed under the room we just left.
            self.logbook.moved(here, self.mapper.moved_at)

    # --- outbound -----------------------------------------------------------

    def send(self, line: str, secret: bool = False) -> None:
        if self._writer is None:
            raise RuntimeError("not connected")
        # One command is one line.  A line break inside it would be a second
        # command nobody typed -- a rule that puts a tell into what it sends
        # could carry one in from another player -- so it goes as a space.
        line = re.sub(r"[\r\n]+", " ", line)
        if not secret and self.login.asking_for_name and line.strip():
            # Typed at 3K's name question: this is who is playing.  Never at
            # the password question, which asking_for_name rules out.
            self.me = line.strip().split(" ")[0]
        # Every outbound line funnels through here -- the queue, scripts, the
        # browser, the jumpstart -- so this is the one place the log has to
        # know about.  A password is the one string that must reach the socket
        # and nowhere else: not the capture, which exists to be replayed and
        # shared, and not the log, which exists to be searched.
        noted = "********" if secret else line
        if self.raw_log is not None:
            self.raw_log.sent(noted)
        if self.mapper is not None and not secret:
            self.mapper.sent(line)
        if self.logbook is not None:
            self.logbook.add("sent", noted)
        # 0xFF is telnet's IAC, and "ÿ" encodes to it: sent bare, the MUD
        # reads whatever follows as a telnet command.  Doubled, it is a letter.
        wire = line.encode(self.encoding, "replace").replace(b"\xff", b"\xff\xff")
        self._writer.write(wire + b"\r\n")

    @property
    def who_am_i(self) -> str:
        """The playing character's name, however they logged in; "" if unknown."""
        char = self.character
        return (getattr(char, "name", "") if char is not None else "") or self.me

    def jumpstart(self) -> None:
        """Announce ourselves so the MUD starts sending MIP.

        Unpadded on the way up (the spec says MUDs sscanf it); the MUD pads to
        five digits on the way down.
        """
        self.jumpstarted = True
        self._last_jumpstart = time.monotonic()
        self.send(f"3klient {self.sec_code}~{self.version}")
