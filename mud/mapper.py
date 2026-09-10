"""Dead reckoning: knowing where you are because you know where you were.

This is about *position*, which is a separate question from geography.  An
imported map answers "what is where"; nothing but dead reckoning answers
"which of those rooms am I standing in", because 3K never says.  A map makes
the job easier -- it starts full instead of empty -- and does not remove it.


Nothing on 3k.org's wire identifies a room.  ``BAD`` names fewer than half of
all arrivals, whole areas share an exit set, and the scenery shifts with the
weather and with whatever is lying on the floor.  So position is inferred from
movement, and what the room looks like is only ever used to check that
inference or to recover it once it is lost.

Two facts, both measured from a walk across town, decide the shape:

*Commands overlap.*  You send ``w`` and then ``n`` 0.3s apart and the first
room block has not arrived yet, so the outstanding commands are a queue and
each block consumes the oldest.

*A queue with no timeout goes permanently wrong.*  The commands at the start of
a session -- ``l``, ``jump``, seven ``aset`` lines -- never produce a room
block, and if they stay queued then every arrival for the rest of the session
is credited to the wrong command.  Round trip measured at a 0.06s median and a
0.67s maximum across 41 moves, so anything outstanding for longer than
``WINDOW`` is treated as having produced nothing at all.
"""

from __future__ import annotations

import heapq
import itertools
import time
from collections import deque
from typing import Iterable

from .store import Store, personal

#: How long a command may wait for its room block.  Ten times the observed
#: median, comfortably past the observed maximum, and well under the 2s tick.
WINDOW = 1.0

#: Rooms added to a locked map: 3K has gained them since it was written.
#: Tagged rather than silently blended in, so they can be looked over and, if
#: they are right, fed back to whatever made the map.
NEW = "new"

#: Commands that redisplay the room without moving you.  This is a convention,
#: not something the protocol states, so it is editable rather than baked in:
#: without it a `look` would be credited with the next room block and drawn as
#: an exit leading to where you already stand.
NON_MOVING = {"look", "l", "glance", "exits", "brief", "map"}


class Mapper:
    """Tracks position and grows the map as you walk.

    ``here`` is the current room id, or ``None`` while lost.  Being lost is a
    normal state -- it is where every session starts, and where a teleport or a
    death puts you -- so it resolves itself as you move rather than raising.
    """

    def __init__(self, store: Store, window: float = WINDOW,
                 non_moving: Iterable[str] | None = None) -> None:
        self.store = store
        self.window = window
        self.non_moving = set(NON_MOVING if non_moving is None else non_moving)
        self.here: int | None = None
        #: Rooms we might be in, while lost.  Narrowed by each move.
        self.candidates: list[int] = []
        #: When the command that caused the last move was sent.  The log uses
        #: it to file an arrival's text under the room it describes.
        self.moved_at: float | None = None
        #: Exits of the last room block, kept so a name arriving on the tick
        #: afterwards can be matched against the room it belongs to.
        self._last_exits: list[str] = []
        #: The last room we were sure of.  Kept after becoming lost, because
        #: it is the best evidence about which of several identical-looking
        #: rooms this one is.
        self._was: int | None = None
        #: Set while a look is being used to find out whether a step moved us.
        #: Only then does "this looks like the room we are already in" mean we
        #: did not move, rather than that we walked somewhere identical.
        self._verifying = False
        self._pending: deque[tuple[float, str]] = deque()

    # --- input --------------------------------------------------------------

    def sent(self, line: str, at: float | None = None) -> None:
        cmd = line.strip().lower()
        if not cmd or cmd in self.non_moving:
            return
        self._pending.append((time.time() if at is None else at, cmd))

    def arrived(self, exits: Iterable[str], scenery: Iterable[str],
                name: str | None = None, at: float | None = None) -> int | None:
        """A room block settled.  Returns the room we believe we are in."""
        now = time.time() if at is None else at
        exits, scenery = list(exits), list(scenery)
        ways = self._ways_out()          # of the room we are leaving, not this one
        self._last_exits = exits

        verifying, self._verifying = self._verifying, False
        if verifying and self._pending:
            # A look is being used to find out what a step did, and the answer
            # is whatever this block says.  Neither the window nor the
            # ordering applies here: a teleport does send a room block, but
            # nothing settles it until the look, so the block opened when the
            # step ran -- older than the command we re-armed, and older than
            # the window allows.
            sent_at, cmd = self._pending.popleft()
        else:
            while self._pending and now - self._pending[0][0] > self.window:
                self._pending.popleft()        # that command moved nothing
            sent_at, cmd = self._blame(ways, now)
        self.moved_at = sent_at

        if cmd is None:
            # Nothing we sent caused this.  Usually a redisplay -- after a
            # kill, or the room re-sent on its own -- but not always: a guild
            # teleport, a follow, a spell moves you with nothing we can point
            # at.  So believe it is a redisplay only while it still looks like
            # the room we think we are in.  Taking that on trust stamped the
            # far end of a teleport onto the room we had just left.
            if (self.here is not None
                    and self.store.consistent(self.here, exits, scenery)):
                self._record(self.here, exits, scenery, name, now, moved=False)
                return self.here
            if self.here is not None:
                self._was = self.here
                self.here = None           # moved by something we cannot see
            found = self._locate(exits, scenery, now, name=name)
            if found is None and name:
                self._last_exits = exits
                self.name_here(name)
                found = self.here
            return found

        if self.here is None:
            return self._locate(exits, scenery, now, cmd=cmd, name=name)

        return self._step(cmd, exits, scenery, name, now, verifying, ways)

    def _ways_out(self) -> set[str]:
        """Commands that could take us out of the room we are standing in.

        DDD lists every way out, and the map knows the ones that are not
        directions -- "climb pipe", "embrace void" -- wherever anybody has
        walked one.
        """
        ways = {e.strip().lower() for e in self._last_exits if e.strip()}
        if self.here is not None:
            ways |= {str(e["command"]).strip().lower()
                     for e in self.store.exits_from(self.here)}
        return ways

    def _blame(self, ways: set[str], now: float) -> tuple[float | None, str | None]:
        """Which command in the queue caused this block.

        Oldest first, because that is the order the MUD ran them in.  A block
        does not settle until the next unrelated message arrives, so by then
        you may already have typed the next command -- and it cannot have
        caused a block that opened before it was sent.

        Except that a route sends its housekeeping and its next step in one
        breath: "wrap all", "disperse corpse", "divvy gold", "w".  Only the
        last of them moves, and FIFO hands the block to "wrap all".  The room
        has no such way out, so the map cannot place it, and the client is
        lost with a perfectly good "w" three places down the queue.  On the
        chessboard route that happened at every single kill.

        So skip past commands the room we are standing in has no way out for.
        They ran and they did something; they did not do this.  Skipped only,
        never reordered: if the oldest is a way out then it is the answer,
        because two moves in flight arrive in the order they were sent.  And
        if none of them is a way out, the oldest is still the best guess --
        3K's exits are what DDD says they are, but a route can walk something
        neither DDD nor the map has heard of, and a wrong guess there is no
        worse than the wrong guess we would have made anyway.
        """
        live = sum(1 for t, _ in self._pending if t <= now)
        if not live:
            return None, None
        pick = next((i for i in range(live)
                     if self._pending[i][1].strip().lower() in ways), 0)
        for _ in range(pick):
            self._pending.popleft()      # it ran, but it did not move us
        return self._pending.popleft()

    # --- moving -------------------------------------------------------------

    def _join(self, here: int, cmd: str, there: int, now: float,
              ways: set[str]) -> None:
        """Record that `cmd` leads from one room to the other -- if it can.

        The map has to be able to learn a way out it was not told about, and
        on 3K those are worth having and impossible to guess.  "embrace void"
        is an emote everywhere in the game except one room in Eastwick, where
        it takes you to the Angels 2.0 area.  A shop has "home", "chaos",
        "science", "smithy" and the rest, which teleport you out.  None of
        them is a direction, none is in DDD, and no rule about the shape of a
        command would find them.

        What it must not do is write down a guess.  Two ways of telling:

        A command does not take you to the room you are already standing in.
        A block that says otherwise is a redisplay -- after a kill, or on the
        tick -- and the room the client was told about is the one it was in.

        And on a locked map, a command that is not a way out, leading
        somewhere the room can already reach by one that is, is the client
        blaming the wrong one of several commands in flight.  Six "wrap all"
        edges and a "disperse corpse" got written across the chess board that
        way, and the panel then drew squares along them -- rooms bleeding into
        a board that is a perfect eight by eight.
        """
        if there == here:
            return
        if self.store.locked and cmd.strip().lower() not in ways:
            known = {e["to_room"] for e in self.store.exits_from(here)
                     if str(e["command"]).strip().lower() in ways}
            if there in known:
                return
        self.store.link(here, cmd, there, now)

    def _step(self, cmd: str, exits: list[str], scenery: list[str],
              name: str | None, now: float, verifying: bool = False,
              ways: set[str] | None = None) -> int:
        here = self.here
        assert here is not None
        ways = self._ways_out() if ways is None else ways
        known = self.store.destination(here, cmd)

        if (verifying and (known is None or not self._fits(known, exits, scenery))
                and self.store.consistent(here, exits, scenery)):
            # The look came back showing the room we were already in, so the
            # step did nothing.  Only safe to conclude while verifying: on a
            # chessboard the room you walk into looks exactly like the one you
            # left, and that is a move.
            self._record(here, exits, scenery, name, now, moved=False)
            return here

        if known is not None and self._fits(known, exits, scenery):
            self._record(known, exits, scenery, name, now)
            self._join(here, cmd, known, now, ways)
            self.here = known
            return known

        # Either we have never walked this way, or it did not lead where it
        # led last time -- a random exit, a door, a world that changed.  A
        # room that already matches is far likelier than a brand new one
        # sharing a fingerprint, but only if exactly one matches: the
        # chessboard is full of squares that match each other.
        hits = [r for r, score in self.store.candidates(exits, scenery)
                if score == 1.0]
        if len(hits) != 1 and self.store.locked:
            # A locked map still has to be able to learn: 3K gains rooms, and
            # a map that can never grow goes stale.  The distinction is in the
            # name.  A room whose name the map has never heard of is genuinely
            # new -- we knew where we were, we walked, and this is somewhere
            # else.  A room whose name the map *does* have, that still did not
            # match, is far likelier to be a failure to recognise it, and
            # adding it would make the duplicate this lock exists to prevent.
            if name and not self.store.by_name(name):
                target = self.store.add_room(name, now)
                self.store.tag(target, NEW)
                self._record(target, exits, scenery, name, now)
                self._join(here, cmd, target, now, ways)
                self.here = target
                return target
            self._was, self.here, self.candidates = here, None, []
            return self._locate(exits, scenery, now, name=name)
        target = hits[0] if len(hits) == 1 else self.store.add_room(name, now)

        self._record(target, exits, scenery, name, now)
        self._join(here, cmd, target, now, ways)
        self.here = self._was = target
        return target

    # --- being lost ---------------------------------------------------------

    def unsure(self) -> None:
        """Stop claiming to know where we are.

        The room is real; we are simply not standing in it any more -- a link
        death, a teleport nothing told us about, or the player saying so.  What
        is kept is ``_was``, because which of several identical-looking rooms
        this one is is a question the last place we were sure of is the best
        evidence for.  What goes is anything in flight: commands waiting to be
        blamed for a room block that is never going to arrive, and the exits of
        a room we have left.
        """
        self.here = None
        self.candidates = []
        self._pending.clear()
        self._last_exits = []


    def _locate(self, exits: list[str], scenery: list[str], now: float,
                cmd: str | None = None, name: str | None = None) -> int | None:
        """Work out where we are from scratch, or narrow it down.

        With a command in hand we can prune: if we were in one of ``n`` rooms
        and walked ``cmd``, we are now in one of the rooms those lead to.  Two
        moves usually settle it; until then we stay honestly lost rather than
        guessing and corrupting the graph.

        The room's own title is the strongest thing we have and the map has one
        for every room, so it is asked first.  What it cannot do is tell two
        rooms of the same name apart, and 3K has sixty-four called "A Dark
        Square" with the same four exits -- which is why this can narrow and
        wait but cannot always answer.
        """
        if name:
            named = self.store.by_name(name, exits)
            if len(named) > 1:
                named = self._nearest(named)
            if len(named) == 1:
                self.here = named[0]
                self.candidates = []
                self._record(self.here, exits, scenery, name, now)
                return self.here
            if named:
                self.candidates = named

        if cmd is not None and self.candidates:
            reachable = {
                dest for room in self.candidates
                if (dest := self.store.destination(room, cmd)) is not None
            }
            narrowed = [r for r in reachable if self._fits(r, exits, scenery)]
            if narrowed:
                self.candidates = narrowed
                if len(narrowed) == 1:
                    self.here = narrowed[0]
                    self.candidates = []
                    self._record(self.here, exits, scenery, None, now)
                    return self.here
                return None

        hits = [r for r, score in self.store.candidates(exits, scenery)
                if score == 1.0]
        if len(hits) > 1:
            hits = self._nearest(hits)
        if len(hits) > 1:
            # Several rooms look like this one.  Stay lost: guessing here is
            # how a map quietly acquires edges that do not exist.
            self.candidates = hits
            return None

        if not hits and self.store.locked:
            # A finished map does not grow.  A room it does not contain is far
            # more likely to be one we failed to recognise, and inventing it
            # adds a duplicate of a room already there that nothing will
            # later join up.
            self.candidates = []
            return None

        # Nothing matches, so this is somewhere we have never been -- which is
        # exactly what the first room of the first session looks like.
        self.here = hits[0] if hits else self.store.add_room(None, now)
        self.candidates = []
        self._record(self.here, exits, scenery, None, now)
        return self.here

    # --- bookkeeping --------------------------------------------------------

    def _fits(self, room_id: int, exits: list[str],
              scenery: list[str]) -> bool:
        return self.store.consistent(room_id, exits, scenery)

    def _record(self, room_id: int, exits: list[str], scenery: list[str],
                name: str | None, now: float, moved: bool = True) -> None:
        self.store.observe(room_id, exits, scenery, now)
        if moved:
            self.store.visit(room_id, name, now)
        else:
            # A redisplay is evidence, not an arrival: it should not inflate
            # the visit count, but a name it carries is still worth keeping.
            self.store.suggest_name(room_id, name)

    #: Exits that step somewhere on the page.  Everything else -- "enter",
    #: "vortex", "climb pipe", "omp" -- is where one area tends to end and the
    #: next begins, which is what makes them a usable boundary.
    SPATIAL = frozenset("n s e w ne nw se sw u d".split())

    def area(self, start: int | None = None, limit: int = 500) -> list[int]:
        """The rooms that look like one area with ``start``.

        Spreads along compass exits and stops at three things: a room already
        claimed by another region, an exit with no direction to it, and the
        limit.  That is the boundary rule the captures suggested -- of the nine
        steps into 3K's chessboard, the two that are not compass moves are
        exactly the two that cross into somewhere new -- and it is a proposal,
        not a verdict.  You correct it afterwards.
        """
        start = self.here if start is None else start
        if start is None:
            return []
        mine = self.store.room(start)
        home = None if mine is None else mine["region_id"]

        found, queue = [], [start]
        seen = {start}
        while queue and len(found) < limit:
            rid = queue.pop(0)
            row = self.store.room(rid)
            if row is None:
                continue
            if rid != start and row["region_id"] not in (None, home):
                continue                       # somebody else's area already
            found.append(rid)
            for edge in self.store.exits_from(rid):
                if str(edge["command"]) not in self.SPATIAL:
                    continue                   # a door out of the area
                nxt = int(edge["to_room"])
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return found

    def expect(self, command: str, at: float | None = None) -> None:
        """Re-arm a command whose reply is still to come.

        A move that sends no room block is followed by a look, and by the time
        that answers, the command is long past its window and has been thrown
        away -- taking with it the one thing that actually knows where we are.
        The map says "embrace void" from that room leads to the Tree of Life;
        the room's name does not, because two of them are called the same.
        """
        self._pending.clear()
        self._pending.append((time.time() if at is None else at, command))
        self._verifying = True

    def _nearest(self, hits: list[int]) -> list[int]:
        """Narrow a tie by where we just were.

        3K keeps upgraded versions of its areas alongside the originals --
        Tree of Life and Tree of Life 2.0, Catacombs and Catacombs 2 -- and
        fourteen of them make 1,138 rooms indistinguishable by name and exits.
        Both versions are real, so neither can simply be preferred.  What can
        be preferred is the one next door to the room we were last sure of:
        you do not cross between two versions of an area by walking.
        """
        if self._was is None or len(hits) < 2:
            return hits
        near = self.store.neighbours(self._was) | {self._was}
        closer = [r for r in hits if r in near]
        return closer or hits

    def name_here(self, name: str) -> None:
        """``BAD`` says what room you are in, on the tick.

        It names wherever you are now, which is not necessarily the block that
        just arrived -- it usually trails it by a room when you are moving
        quickly.  And when we are lost it is the way back in: on an imported
        map every room has a name already, so being told one is often enough
        to say where we are standing.
        """
        if self.here is not None:
            self.store.suggest_name(self.here, name)
            return
        hits = self.store.by_name(name, self.store.fingerprint(
            self._last_exits, ())[0].split(",") if self._last_exits else None)
        if len(hits) > 1:
            hits = self._nearest(hits)
        if len(hits) == 1:
            self.here, self.candidates = hits[0], []
        elif hits:
            # Narrowed but not settled -- a thousand rooms are called "A
            # battleground".  Walking prunes it.
            self.candidates = hits

    def status(self) -> dict:
        room = None if self.here is None else self.store.room(self.here)
        return {
            "room": self.here,
            "name": None if room is None else room["name"],
            "region": [] if self.here is None
                      else self.store.region_path(self.here),
            "visits": None if room is None else room["visits"],
            "lost": self.here is None,
            "candidates": len(self.candidates),
            # Not "rooms": the drawn neighbourhood claims that name, and a
            # count arriving where the browser expects a map reads to it as a
            # server too old to send one.
            "known_rooms": self.store.db.execute(
                "SELECT COUNT(*) c FROM room").fetchone()["c"],
            "edges": self.store.db.execute(
                "SELECT COUNT(*) c FROM edge").fetchone()["c"],
            "exits": {
                str(e["command"]): int(e["to_room"])
                for e in (self.store.exits_from(self.here) if self.here else [])
            },
        }

    def neighbourhood(self, radius: int = 10, centre: int | None = None,
                      limit: int = 250, area_only: bool = True) -> dict:
        """The rooms worth drawing: the area you are standing in.

        An area is what a person means by "where I am", and 3K's map has 777
        of them.  Spreading ten moves outward instead crossed into three
        neighbouring areas at once and drew the links between them, which is
        a great deal of ink about geography nobody was looking at.

        Still bounded by radius and by a room cap, because an area can be
        four thousand rooms, and this runs a query per room several times a
        second to fill a panel that holds perhaps sixty.  Rooms with no area
        at all fall back to spreading, which is what a map being built by
        hand looks like before anything has been labelled.
        """
        centre = self.here if centre is None else centre
        if centre is None:
            return {"centre": None, "rooms": {}}

        home = self.store.room(centre)
        area = None if home is None or not area_only else home["region_id"]

        rooms: dict[int, dict] = {}
        frontier, depth = [centre], 0
        while frontier and depth <= radius and len(rooms) < limit:
            nxt = []
            for rid in frontier:
                if rid in rooms or len(rooms) >= limit:
                    continue
                row = self.store.room(rid)
                if row is None:
                    continue
                if area is not None and row["region_id"] != area and rid != centre:
                    continue
                links: dict[str, int] = {}
                for edge in self.store.exits_from(rid):
                    links.setdefault(str(edge["command"]), int(edge["to_room"]))
                rooms[rid] = {
                    "name": row["name"],
                    "visits": row["visits"],
                    "region": row["region_id"],
                    "area": self.store.region_path(rid),
                    "exits": links,
                    # Ways out the MUD has told us about that nobody has
                    # walked: the whole point of having a map is seeing where
                    # you have not been.
                    "unwalked": [e for e in self.store.exits_of(rid)
                                 if e not in links],
                }
                # Spread both ways: a room you walked in from is next door on
                # the page even when nothing leads back to it yet.  Each room
                # still reports only the exits it actually has.
                nxt.extend(self.store.neighbours(rid))
            frontier, depth = nxt, depth + 1
        return {"centre": centre, "rooms": rooms}

    # --- routing ------------------------------------------------------------

    def find_rooms(self, text: str) -> list[tuple[int, str, int]]:
        """Rooms whose name matches, nearest first by route length.

        Names are not unique -- 3K has two Alchemy rows and several Eastwicks
        -- so this returns every match and lets the caller say which.
        """
        like = f"%{text.strip().lower()}%"
        found = []
        for row in self.store.db.execute(
            "SELECT id, name FROM room WHERE name IS NOT NULL "
            "AND LOWER(name) LIKE ? ORDER BY visits DESC", (like,)
        ):
            route = self.route(int(row["id"]))
            if route is not None:
                found.append((int(row["id"]), row["name"], len(route)))
        found.sort(key=lambda r: r[2])
        return found

    #: What a way out that has already failed is worth avoiding.  Not
    #: infinite: a locked door opens, a spell comes back, and a route that
    #: refuses to consider anything that once failed is a route that gives up
    #: on the map.
    FAILED = 40.0

    @staticmethod
    def cost(command: str, failed: int = 0) -> float:
        """What a step is worth avoiding.

        Counting every exit as one step produces routes that are shortest and
        useless: an imported map is full of shortcuts -- recalls, portals,
        somebody's ``.gohome`` alias -- and a nine-step path through four of
        them is worse than twenty plain directions.  Walking is cheap, doors
        cost a little, and anything that is plainly a client command rather
        than a MUD one is a last resort.
        """
        if command in Mapper.SPATIAL:
            return 1.0 + Mapper.FAILED * min(failed, 3)
        penalty = Mapper.FAILED * min(failed, 3)
        if command.startswith((".", "#", "$")):
            return 100.0 + penalty        # a tt++ alias; it may not exist here
        return (3.0 if ";" in command else 2.0) + penalty

    def route(self, dest: int, start: int | None = None) -> list[str] | None:
        """Cheapest sequence of commands from here to ``dest``.

        Over the flat graph.  Regions never take part: a hierarchy is a way of
        drawing the map, and routing through it is how mappers end up
        producing paths that are wrong at the boundaries.
        """
        start = self.here if start is None else start
        if start is None:
            return None
        if start == dest:
            return []

        seen: set[int] = set()
        queue = [(0.0, 0, start, [])]        # (cost, tie-break, room, path)
        counter = itertools.count()
        while queue:
            spent, _, room, path = heapq.heappop(queue)
            if room in seen:
                continue
            seen.add(room)
            if room == dest:
                return path
            for edge in self.store.exits_from(room):
                nxt = int(edge["to_room"])
                if nxt in seen:
                    continue
                command = str(edge["command"])
                if personal(command):
                    continue            # yours goes somewhere else, or nowhere
                step = self.cost(command, int(edge["failed"] or 0))
                heapq.heappush(queue, (spent + step,
                                       next(counter), nxt, path + [command]))
        return None
