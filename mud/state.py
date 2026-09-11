"""Live world state, rebuilt from MIP messages.

Everything here is *pushed* by the MUD, so none of it is scraped.  Handlers
register for changes and are called with (name, new, old).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Callable

from . import codes, events
from .codes import Chat, GlineField, RoomObject, Tell
from .events import Bus

Listener = Callable[[str, object, object], None]


@dataclass
class Player:
    hp: int | None = None
    max_hp: int | None = None
    sp: int | None = None
    max_sp: int | None = None
    gp1: int | None = None
    max_gp1: int | None = None
    gp2: int | None = None
    max_gp2: int | None = None
    gline1: str = ""
    gline2: str = ""
    enemy: str = ""
    enemy_pct: int | None = None
    enemy_image: str = ""

    @staticmethod
    def _pct(cur: int | None, mx: int | None) -> float | None:
        if cur is None or not mx:
            return None
        return round(100.0 * cur / mx, 1)

    @property
    def hp_pct(self) -> float | None:
        return self._pct(self.hp, self.max_hp)

    @property
    def sp_pct(self) -> float | None:
        return self._pct(self.sp, self.max_sp)

    @property
    def gline(self) -> dict[str, GlineField]:
        """Guild state lifted out of the colour markup in both guild lines."""
        merged = dict(codes.parse_gline(self.gline1))
        merged.update(codes.parse_gline(self.gline2))
        return merged


@dataclass
class Room:
    short: str = ""
    exits: list[str] = field(default_factory=list)
    #: When the block that describes this room began arriving.  The mapper
    #: matches arrivals against the command that caused them within a second,
    #: and a block does not settle until the next unrelated message -- up to a
    #: tick later -- so settling time would put the move outside the window.
    opened_at: float | None = None
    #: HAA records -- things you can act on (npc / player / item)
    contents: list[RoomObject] = field(default_factory=list)
    #: HAB records -- scenery nouns you can examine
    scenery: list[RoomObject] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[RoomObject]:
        return [o for o in self.contents if o.kind == kind]

    def mobs(self) -> list[RoomObject]:
        return self.of_kind("npc")

    def players(self) -> list[RoomObject]:
        return self.of_kind("player")

    def items(self) -> list[RoomObject]:
        return self.of_kind("item")

    def find(self, name: str) -> RoomObject | None:
        want = name.lower()
        for o in self.contents:
            if want in o.name.lower():
                return o
        return None


class World:
    """Applies MIP messages to state and reports what changed."""

    def __init__(self, bus: Bus | None = None) -> None:
        self.bus = bus or Bus()
        self.player = Player()
        self.room = Room()
        self.caption = ""
        self.uptime = ""
        self.reboot = ""
        self.mudlag = ""
        self.editing = ""
        self.combat_special = ""
        self.guild_special = ""
        self.enemy_label = ""          # 3k.org sends this via AAB, not M
        #: BBA/BBB/BBC/BBD -- Portal calls these "masks", but they are simply
        #: the display names for the gauges (UpdateMasks assigns them as the
        #: hint on GaugeGP1 and friends).  3k.org has never been observed to
        #: send them, so these stay empty and the UI falls back to your own.
        self.labels: dict[str, str] = {}
        self.tells: deque[Tell] = deque(maxlen=500)
        #: The last few lines 3K printed, as the player sees them: how a tell
        #: is told from a soul (codes.told).
        self.recent: deque[str] = deque(maxlen=6)
        self.chat: deque[Chat] = deque(maxlen=1000)
        #: tells and channels in arrival order, for the monitor
        self.messages: deque[dict] = deque(maxlen=500)
        self.unknown_codes: dict[str, int] = {}
        self._listeners: list[Listener] = []
        self._event_listeners: list[Callable[[str, object], None]] = []
        self._last_code: str | None = None
        self._room_open_at: float | None = None
        #: The two halves of a soul you do at a distance (see _own_soul): the
        #: `~you~` half held until the other says who it went to, and the
        #: words of an `x~` half that came first.
        self._echo: Tell | None = None
        self._paired: str | None = None

    def on_change(self, fn: Listener) -> Listener:
        self._listeners.append(fn)
        return fn

    def on_event(self, fn: Callable[[str, object], None]):
        """Discrete events -- tells, chat -- as opposed to state changes."""
        self._event_listeners.append(fn)
        return fn

    #: Set by the session when there is somewhere to write.  Tells and chat
    #: are logged as themselves rather than only as raw output lines, so
    #: "everything one player said" is one query rather than a guess at their wording.
    log_to = None

    def log(self, kind: str, text: str, channel: str, who: str) -> None:
        if self.log_to is not None:
            self.log_to.add(kind, text, channel, who)

    def _emit(self, kind: str, obj: object) -> None:
        self.bus.emit(kind, obj)
        for fn in self._event_listeners:
            fn(kind, obj)

    def _set(self, obj: object, name: str, value: object) -> None:
        old = getattr(obj, name, None)
        if old == value:
            return
        setattr(obj, name, value)
        self.bus.emit(events.STATE, name, value, old)
        for fn in self._listeners:
            fn(name, value, old)

    def apply(self, code: str, data: str) -> None:
        # A room block is a DDD plus the run of H** records after it, and it
        # has settled once anything unrelated arrives -- or 3K's prompt, which
        # the session passes on as settle().  Waiting for the records
        # themselves would miss a room that has neither scenery nor contents
        # -- rare, but one missed room puts dead reckoning off by one for the
        # rest of the session.
        if self._echo is not None and not (code == "BAB" and self._completes(data)):
            self.flush_echo()
        if code != "BAB":
            self._paired = None
        opening = code == "DDD" and self._last_code != "BAD"
        if opening or code not in codes.ROOM_RECORD_CODES:
            # A new block clears the old room, so tell anyone waiting on the
            # previous one before that happens.
            self.settle()
        try:
            self._apply(code, data)
        finally:
            if opening:
                self._room_open_at = time.time()
            self._last_code = code

    # --- tells and souls ------------------------------------------------------

    def _tell(self, tell: Tell) -> None:
        self.tells.append(tell)
        self.messages.append({
            "kind": "tell", "at": time.time(), "who": tell.who,
            "channel": "soul" if tell.soul else "tell",
            "text": tell.message, "mine": tell.from_me,
            "soul": tell.soul,
        })
        self._emit("tell", tell)
        self.log("tell", tell.message, "tell", tell.who)

    def _own_soul(self, tell: Tell) -> bool:
        """Is this the `~you~` half of a soul you did at a distance?

        3K sends those twice, in either order, back to back:

            BAB~you~moo at Someone.
            BABx~Someone~you moo at Someone.

        and prints "From afar, you moo at Someone." once.  Taken as two tells
        the first was a tell *to* you, from "you" -- your own moo shown twice,
        with a ding and an unread mark for it.  The `x~` half is the one kept:
        it says who it went to, which is who a click replies to.

        Held rather than dropped, until the next message: a `~you~` with no
        other half is shown after all.
        """
        if tell.from_me or tell.who != "you":
            return False
        if self._paired is not None and self._paired == tell.message:
            self._paired = None                   # its other half came first
            return True
        self._echo = replace(tell, soul=True)
        return True

    def _completes(self, data: str) -> bool:
        """Is this BAB the other half of the `~you~` being held?"""
        other = codes.parse_bab(data)
        return other.from_me and other.message == f"you {self._echo.message}"

    def flush_echo(self) -> None:
        """A `~you~` whose other half never came is a soul like any other."""
        echo, self._echo = self._echo, None
        if echo is not None:
            self._tell(echo)

    def settle(self) -> None:
        """The room block that is open has finished: say so.

        Anything unrelated arriving finishes it, and so does 3K's prompt,
        which ends every reply.  Walking, the next room comes at once; in a
        quiet room nothing else may come for seconds -- after `embrace void`
        the temple doorway sent nothing for six, and a look answered straight
        away read as unanswered.
        """
        if self._room_open_at is None:
            return
        self.room.opened_at = self._room_open_at
        self._room_open_at = None
        self.bus.emit(events.ROOM, self.room)

    def titled_room(self, exits, at: float, contents_from: int = 0,
                    scenery_from: int = 0) -> None:
        """A room that arrived as its title alone.

        In brief mode 3K sends no DDD with a step -- the title, the contents,
        and then only the periodic BAD-and-DDD sample a second or two later,
        which is deliberately not a new room -- so without this no room block
        ever opened and the map stood still until somebody typed look.  The
        session calls this when a marked title has had no DDD of its own.

        The contents that arrived after the title are the new room's; anything
        from before is the old one's.  The room goes out at once, stamped with
        the title's time, which is when the move happened.
        """
        new_contents = self.room.contents[contents_from:]
        new_scenery = self.room.scenery[scenery_from:]
        if self._room_open_at is not None:
            # A block still open is the previous room's: let it finish first.
            del self.room.contents[contents_from:]
            del self.room.scenery[scenery_from:]
            self.room.opened_at = self._room_open_at
            self._room_open_at = None
            self.bus.emit(events.ROOM, self.room)
        self.room.contents[:] = new_contents
        self.room.scenery[:] = new_scenery
        self._set(self.room, "exits", list(exits))
        self.room.opened_at = at
        self.bus.emit(events.ROOM, self.room)

    def _apply(self, code: str, data: str) -> None:
        if code == "FFF":
            values, unknown = codes.parse_composite(data)
            for name, value in values.items():
                self._set(self.player, name, value)
            if values.get("enemy") == "":
                # The fight is over.  3K says so by emptying the enemy -- in
                # all 137 fights in the captures -- but never sends its
                # health as 0 (the last it sends is the round before it
                # died) and never clears the AAB label.  Left alone, the
                # enemy panel stayed up after the kill, with that name and
                # that last health.
                self._set(self.player, "enemy_pct", None)
                self._set(self, "enemy_label", "")
            for tag in unknown:
                self._count_unknown(f"FFF:{tag}")

        elif code == "DDD":
            # DDD arrives in two distinct roles, which a capture makes obvious
            # but the wire does not announce:
            #
            #   DDD + H** records        -> genuine room entry
            #   BAD then DDD, no records -> periodic refresh, same exits
            #
            # Across 43 observed DDDs the split is exact: every BAD-preceded
            # DDD carried no contents, every standalone one did.  Clearing on
            # both would empty the room a couple of seconds after entering it.
            if self._last_code != "BAD":
                self.room.contents.clear()
                self.room.scenery.clear()
            self._set(self.room, "exits", codes.parse_ddd(data))

        elif code == "HAA":
            self.room.contents.append(codes.parse_haa(data))

        elif code == "HAB":
            self.room.scenery.append(codes.parse_hab(data))

        elif code == "BAB":
            tell = codes.parse_bab(data)
            if self._own_soul(tell):
                return
            tell = replace(tell, soul=not codes.told(tell, self.recent))
            if tell.from_me and tell.soul and tell.message.startswith("you "):
                if self._echo is not None:
                    self._echo = None                 # its other half, held
                else:
                    self._paired = tell.message[4:]   # the other half is next
            self._tell(tell)

        elif code == "CAA":
            chat = codes.parse_caa(data)
            self.chat.append(chat)
            self.messages.append({
                "kind": "chat", "at": time.time(), "who": chat.who,
                "channel": chat.channel, "command": chat.command,
                "text": chat.message, "mine": False,
            })
            self._emit("chat", chat)
            self.log("chat", chat.message, chat.channel, chat.who)

        elif code == "AAB":
            # Spec says <filename>~<label> for an image.  3k.org sends an empty
            # filename and puts the enemy's name and condition in the label.
            _, label = codes.fields(data, 2)[:2]
            # Only during a fight: one that trails in after the enemy has
            # gone would put the panel back up for a creature already dead.
            if self.player.enemy:
                self._set(self, "enemy_label", label)

        elif code in codes.SIMPLE:
            attr = codes.SIMPLE[code]
            target = self.room if attr == "room_short" else self
            self._set(target, "short" if attr == "room_short" else attr, data)

        elif code in codes.GAUGE_LABELS:
            name = codes.GAUGE_LABELS[code]
            if self.labels.get(name) != data:
                self.labels[name] = data
                self.bus.emit(events.STATE, f"label:{name}", data, None)

        elif code in codes.KNOWN_UNHANDLED:
            pass

        else:
            self._count_unknown(code)

    def _count_unknown(self, code: str) -> None:
        self.unknown_codes[code] = self.unknown_codes.get(code, 0) + 1
