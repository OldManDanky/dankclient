"""Walking a route and fighting what you meet, as a script writes it.

tt++ does this by matching room descriptions and hoping.  MIP does not need to
hope: ``DDD`` says which ways out exist, ``HAA`` names every creature in the
room *and lists the commands the MUD will accept for it* -- so attacking is not
a guessed "kill %1" but the game's own ``kill #N`` with the name it gave us.

The primitives are async and cancellable, so a route reads as what it is::

    TARGETS = {"Cur", "Cancer"}

    @bot("tradepost")
    async def circuit():
        while True:
            for step in "n n e s w".split():
                await walk(step)
                for mob in room.mobs():
                    if mob.name in TARGETS:
                        await attack(mob)

and the declarative form builds exactly that loop for the common case::

    patrol("n n e s w", targets=["Cur", "Cancer"])

Two things are enforced rather than left to the script.  A bot stops when it
drops below a health floor, because an unattended walker that keeps stepping
into rooms at ten percent is how a character dies.  And every command still
goes through the pacing queue, so a route cannot outrun the APM ceiling: 3K
does not count movement, but it counts everything else, and a bot that fights
its way round a circuit is spending that budget like anyone else.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from . import events
from .outbound import HIGH, NORMAL

#: Below this, stop.  A percentage, because max hp changes with the character.
HEALTH_FLOOR = 40.0

#: How long to wait for a room block before deciding a move failed.  Generous
#: next to the 0.67s worst case measured across a town walk.
MOVE_TIMEOUT = 3.0

#: A stacked walk: allowance per step on top of MOVE_TIMEOUT.  3K runs a
#: stack back to back (six rooms in 0.07s), so this is generous.
STACK_STEP = 0.05

#: A kill command that has not started a fight in this many seconds did not
#: take.  Once one has started there is no limit: some of 3K's creatures take
#: hundreds of rounds, and a bot that gave up on a fight at two minutes walked
#: off and left its target bleeding.  The health floor still stops it.
START_TIMEOUT = 10.0

#: How often a fight with nothing new to say is checked on.
FIGHT_POLL = 5.0

#: What to send when a step produced nothing, to find out whether it moved
#: you.  Filtered from the pending queue like any look, so the room block it
#: produces is uncaused -- which is exactly right: if it shows somewhere new,
#: the mapper relocates rather than crediting the step.
LOOK = "l"
LOOK_TIMEOUT = 2.0


def wanted(mob, targets: Iterable[str]) -> bool:
    """Is this creature one we are hunting?

    tt++ needs two fields per target -- the long name to recognise it by, and
    a keyword to type at it -- because all it has is the room description.
    HAA carries both, so one list serves: a target matches the short name
    exactly, or appears anywhere in the long one.

        "Sandalphon"  matches npc~Sandalphon~Sandalphon, archangel of Malkuth
        "archangel"   matches all ten of them

    Exact on the name, whole words in the description.  A bare substring
    would make "Sandal" match Sandalphon, and a target list is not the place
    to discover that a half-typed name attacks something.
    """
    name = (getattr(mob, "name", "") or "").lower()
    long = (getattr(mob, "description", "") or "").lower()
    for target in targets:
        want = target.strip().lower()
        if not want:
            continue
        if want == name:
            return True
        if re.search(rf"\b{re.escape(want)}\b", long):
            return True
    return False


class Stopped(Exception):
    """Raised inside a bot when its guard says to stop."""


@dataclass
class Bot:
    name: str
    owner: str
    task: asyncio.Task | None = None
    started: float = 0.0
    steps: int = 0
    kills: int = 0
    note: str = ""
    #: How far through its path it has got -- steps done this lap -- and the
    #: room that left it in.  What Pause keeps, so Resume can go back there.
    at: int = 0
    room: int | None = None
    #: A walk to somewhere: where to, and how many steps -- for the Bot panel.
    goal: str = ""
    length: int = 0

    @property
    def running(self) -> bool:
        # Not once it has been told to stop: a cancel lands on the loop's
        # next turn, and the list sent straight back from Stop said it was
        # still walking until the next push.
        return (self.task is not None and not self.task.done()
                and not self.task.cancelling())


class Bots:
    """Every running bot, so there is one place to see and stop them.

    An admin's client should never leave you guessing whether something is
    walking your character around, so this is surfaced rather than buried.
    """

    def __init__(self, session) -> None:
        self.session = session
        self.bots: dict[str, Bot] = {}

    def start(self, name: str, coro_fn: Callable, owner: str = "script") -> Bot:
        self.stop(name)
        bot = Bot(name=name, owner=owner)
        self.bots[name] = bot

        async def run() -> None:
            try:
                await coro_fn()
                # Only if it did not say anything more useful: a route that
                # stopped because a step went nowhere has already explained
                # itself, and "finished" would paper over that.
                bot.note = bot.note or "finished"
            except asyncio.CancelledError:
                bot.note = "stopped"
                raise
            except Stopped as why:
                bot.note = str(why) or "stopped by guard"
            except Exception as err:
                bot.note = f"failed: {err!r}"
                raise

        bot.task = asyncio.ensure_future(run())
        return bot

    def stop(self, name: str) -> bool:
        bot = self.bots.get(name)
        if bot is None or not bot.running:
            return False
        bot.task.cancel()
        return True

    def stop_all(self) -> int:
        return sum(1 for name in list(self.bots) if self.stop(name))

    @property
    def running(self) -> list[Bot]:
        return [b for b in self.bots.values() if b.running]

    def status(self) -> list[dict]:
        return [
            {"name": b.name, "owner": b.owner, "running": b.running,
             "steps": b.steps, "kills": b.kills, "note": b.note}
            for b in self.bots.values()
        ]


# --- the primitives a script gets --------------------------------------------


def make_api(session, bots: Bots, owner: str) -> dict:
    world, bus = session.world, session.bus

    def check() -> None:
        hp = world.player.hp_pct
        if hp is not None and hp < HEALTH_FLOOR:
            raise Stopped(f"health {hp:.0f}% is below the {HEALTH_FLOOR:.0f}% floor")

    async def gate() -> None:
        """Wait here while the deadman has tripped, then carry on.

        Before each thing a bot sends, rather than dropping what it sends: a
        step dropped mid-route reads as a step that went nowhere, and the
        route would stop instead of pausing.
        """
        deadman = getattr(session, "deadman", None)
        if deadman is not None:
            await deadman.wait()

    async def walk(direction: str, timeout: float = MOVE_TIMEOUT):
        """Take one step and wait to arrive.  None if we did not move.

        A step may be more than one command -- "lift grate;d" appears
        forty-seven times in the imported map -- so a semicolon sends both and
        only the last one is waited on.

        Silence does not mean you did not move.  "embrace void" teleports you
        into the Tree of Life and sends no room block at all: the client
        waited, decided the step had failed, worked out a new route from a
        room it had already left, and the cheapest way out of that room was
        to embrace the void again.  So when nothing arrives, look -- which is
        what a person does, and what settles it either way.
        """
        check()
        parts = [p.strip() for p in direction.split(";") if p.strip()]
        for part in parts:
            await gate()
            # Directions do not count against APM, so they go straight out;
            # the queue still meters anything that is not one.
            if session.apm.is_directional(part, world.room.exits):
                session.queue.now(part)
            else:
                session.queue.put(part, HIGH)
        room = await bus.wait(events.ROOM, timeout)
        if room is not None:
            return room
        # Nothing came back.  Ask -- and tell the mapper the step is still
        # outstanding, because by the time a look answers, the command that
        # would explain where we are has aged out of its window.
        mapper = getattr(session, "mapper", None)
        if mapper is not None and parts:
            mapper.expect(parts[-1])
        await gate()
        session.queue.put(LOOK, HIGH)
        return await bus.wait(events.ROOM, LOOK_TIMEOUT)

    async def attack(target, timeout: float | None = None):
        """Attack, and wait until the fight is over.

        The command comes from the MUD's own list for that creature, so this
        works for anything HAA describes without knowing 3K's verbs.  True
        once the fight has ended; False if it never began.  No time limit once
        it has, unless a script passes one.
        """
        check()
        name = getattr(target, "name", str(target))
        actions = getattr(target, "actions", None) or []
        verb = next((a for a in actions if a.split()[0] in ("kill", "attack")),
                    "kill #N")
        await gate()
        session.queue.put(verb.replace("#N", name), HIGH)

        loop = asyncio.get_running_loop()
        begun = False
        start_by = loop.time() + START_TIMEOUT
        give_up = None if timeout is None else loop.time() + timeout
        while give_up is None or loop.time() < give_up:
            enemy = await bus.wait(events.ENEMY, FIGHT_POLL)
            check()
            if enemy is not None and not enemy:
                return True                     # "" means the fight ended
            # An enemy seen at all means it began -- even if it had already
            # ended again by the time this woke to look.
            begun = begun or bool(enemy) or bool(world.player.enemy)
            if begun and not world.player.enemy:
                return True
            if not begun and loop.time() >= start_by:
                return False                    # the kill never took
        return False

    async def glance(timeout: float = LOOK_TIMEOUT):
        """Look at the room again without moving, and wait for it.

        3K's short look: the room's contents come back fresh, so a creature
        that died is gone from them and one that is still here is still here.
        """
        check()
        await gate()
        session.queue.put("glance", HIGH)
        return await bus.wait(events.ROOM, timeout)

    async def arrive(timeout: float = MOVE_TIMEOUT):
        """Wait for the next room without sending anything."""
        return await bus.wait(events.ROOM, timeout)

    async def dash(route, dest: int, name: str = "speedwalk") -> bool:
        """Send the whole way at once, then wait to arrive.

        A walk that waits for each room to settle before the next step goes
        at one step a round: a room settles on the next message, and between
        steps that is 3K's two-second sample -- 43 walks in the captures went
        out a median 1.99s apart.  3K runs a stack of moves back to back, so
        the stack is the speedwalk, and the map is told the commands queue
        behind each other so it follows every room.  Nothing sent can be
        taken back; a stack that does not arrive falls back to walking.
        """
        mapper = getattr(session, "mapper", None)
        if mapper is None:
            return False
        check()
        await gate()
        # The bot is left alone: this may be a route walking to its start or
        # back to a pause, and those steps are not the route's own.
        commands = [p.strip() for step in route for p in step.split(";")
                    if p.strip()]
        mapper.stacking = True
        try:
            for command in commands:
                session.queue.auto_now(command)
        finally:
            mapper.stacking = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MOVE_TIMEOUT + STACK_STEP * len(commands)
        while mapper.here != dest:
            left = deadline - loop.time()
            if left <= 0:
                break
            await bus.wait(events.ROOM, min(left, 0.5))
        else:
            return True
        # Silence does not mean the last step went nowhere: a teleport sends
        # no room.  With the map one step short, look before anything goes out
        # again -- walking that step again from where it had really taken us
        # sent "embrace void" a second time, from the temple doorway.
        if commands and mapper.route(dest) == [commands[-1]]:
            mapper.expect(commands[-1])
            await gate()
            session.queue.put(LOOK, HIGH)
            await bus.wait(events.ROOM, LOOK_TIMEOUT)
        return mapper.here == dest

    async def travel(dest: int, name: str = "speedwalk", tries: int = 4):
        """Walk to a room, working around ways out that turn out not to work.

        An imported map is a hypothesis.  It holds commands that have stopped
        working, personal shortcuts nobody else can type, doors that are now
        locked -- and no inspection separates those from the real exits, so
        walking is what finds out.  A step that goes nowhere is recorded
        against that edge and the route is worked out again from where we
        actually are, which both gets there and leaves the map better than it
        was found.
        """
        mapper = getattr(session, "mapper", None)
        if mapper is None:
            return False
        # The whole way at once first; walking it room by room is for when
        # that did not get there, and is what finds and marks a bad way out.
        if mapper.here != dest:
            first = mapper.route(dest)
            if first and await dash(first, dest, name):
                return True
        for _ in range(tries):
            if mapper.here == dest:
                return True
            route = mapper.route(dest)
            if not route:
                return mapper.here == dest
            for step in route:
                start = mapper.here
                if await walk(step):
                    if start is not None:
                        mapper.store.mark_worked(start, step)
                    continue
                if start is not None:
                    mapper.store.mark_failed(start, step)
                break
            else:
                return mapper.here == dest
        return False

    async def follow(route, name: str = "speedwalk"):
        """Walk a route one step at a time.

        A speedwalk is not a burst of commands: after the first step you are
        somewhere else, and every step after that is being sent from a room it
        was not meant for.  So each waits for the room block the last one
        produced, and a step that goes nowhere stops the walk rather than
        running the rest of the path blind.
        """
        bot = bots.bots.get(name)
        for step in route:
            if not await walk(step):
                if bot is not None:
                    bot.note = f"{step!r} did not go anywhere"
                return False
            if bot is not None:
                bot.steps += 1
        return True

    def bot(name: str):
        def deco(fn):
            bots.start(name, fn, owner)
            return fn
        return deco

    def patrol(path: str | Iterable[str], targets: Iterable[str] = (),
               name: str = "patrol", loop: bool = True, rest: float = 0.0):
        """The tt++ shape: a route, and what to kill along it."""
        steps = path.split() if isinstance(path, str) else list(path)
        targets = list(targets)

        async def run() -> None:
            while True:
                for step in steps:
                    bots.bots[name].steps += 1
                    await walk(step)
                    for mob in world.room.mobs():
                        if wanted(mob, targets):
                            if await attack(mob):
                                bots.bots[name].kills += 1
                    if rest:
                        await asyncio.sleep(rest)
                if not loop:
                    return

        return bots.start(name, run, owner)

    return {"walk": walk, "attack": attack, "arrive": arrive, "glance": glance,
            "follow": follow, "travel": travel, "dash": dash, "bot": bot, "patrol": patrol, "bots": bots,
            "stop_bots": bots.stop_all}
