"""Routes you build in the UI rather than in a script.

Same shape as the rule store: plain data, edited in the browser, saved as
JSON, and run through exactly the primitives a script would use.  A route is
nothing but a name, a list of directions and what to attack along the way --
which is all the tt++ botpath ever was -- so there is no reason to make
somebody open an editor for it.

A route runs once and stops at the end unless it is set to loop.  That is the
safer default by a distance: a route that quietly starts over is a route still
walking your character around an hour after you stopped watching.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .patrol import wanted

#: How many times one step may be repeated.  A cap, because "999n" in a path
#: is a typo far more often than it is a plan.
MAX_REPEAT = 99


@dataclass
class Route:
    id: str = ""
    name: str = ""
    path: str = ""
    #: Creature names to attack on sight, as MIP spells them.
    targets: list[str] = field(default_factory=list)
    loop: bool = False
    #: Seconds to pause in each room.  Nothing forces this; it is for routes
    #: that want to let a regeneration tick land.
    rest: float = 0.0
    #: Commands to send before the first step.  A Section Z route
    #: opens with "touch angel rune", and a route that walks in without it is
    #: a route walking into a fight it has not prepared for.
    setup: str = ""
    #: The room the path is written from.  A route walked from anywhere else
    #: is fifty steps through the wrong part of the world, so the client goes
    #: there first and checks it arrived.  0 means "wherever I am".
    start: int = 0
    #: Wait rather than fight while another player is in the room.  3kdb has
    #: this on every bot it defines, and it is simple courtesy: nobody wants
    #: their kill taken by somebody else's script.
    polite: bool = False
    enabled: bool = True

    def __post_init__(self) -> None:
        self.id = self.id or uuid.uuid4().hex[:8]
        if isinstance(self.targets, str):
            self.targets = [t.strip() for t in self.targets.split(",") if t.strip()]

    @staticmethod
    def _split(path: str) -> list[str]:
        """Split on separators, except inside braces.

        A braced group is one step made of several commands -- 3kdb's
        treehouse route steps up a tree with "{pick fruit;get seed;d}" -- and
        164 of its 172 routes use them.  Splitting through the braces turns
        one step into three, in a path where the order is the whole point.
        """
        out, buf, depth = [], [], 0
        for ch in path:
            if ch == "{":
                depth += 1
                if depth == 1:
                    continue
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    continue
            elif depth == 0 and ch in ",;\n":
                out.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
        out.append("".join(buf))
        return [piece.strip() for piece in out]

    def setup_steps(self) -> list[str]:
        """The commands to send first, one per line or semicolon.

        Never split on whitespace: these are commands, and "touch angel rune"
        is one of them rather than three.
        """
        return [c.strip() for c in re.split(r"[;\n]", self.setup) if c.strip()]

    def steps(self) -> list[str]:
        """Split a path the way a person would write one.

        Commas, semicolons or newlines separate the pieces when there are
        any, so a step of more than one word survives -- "n, climb pipe, e" --
        and a tt++ path pastes in unchanged, since that is what tt++ uses.
        Without them, whitespace does, which is the ordinary case.

        A leading count repeats a step: "3n", "3 n" and "2 enter" all work,
        which is how MUD clients have spelled it for thirty years.  The count
        only applies when what follows is a single word, so "2 handed sword"
        stays the one thing it obviously is.
        """
        pieces = (self._split(self.path) if re.search(r"[,;{\n]", self.path)
                  else self.path.split())

        out: list[str] = []
        pending = 0                       # a bare "3" waiting for its step
        for piece in pieces:
            step = piece.strip()
            if not step:
                continue
            if step.isdigit():
                pending = min(int(step), MAX_REPEAT)
                continue
            count, repeat = 1, re.fullmatch(r"(\d+)\s*(\S+)", step)
            if repeat:
                count, step = min(int(repeat.group(1)), MAX_REPEAT), repeat.group(2)
            if pending:
                count, pending = pending, 0
            out.extend([step] * count)
        return out

    def validate(self) -> str | None:
        if not self.name.strip():
            return "give it a name"
        if not self.steps():
            return "no directions in the path"
        return None


class RouteStore:
    def __init__(self, host, path: str | Path = "scripts/routes.json") -> None:
        self.host = host                      # ScriptHost, for its Bots
        self.path = Path(path)
        self.routes: list[Route] = []

    # --- persistence --------------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            self.routes = []
            return
        try:
            raw = json.loads(self.path.read_text())
        except (ValueError, OSError):
            self.routes = []
            return
        self.routes = [Route(**r) for r in raw if isinstance(r, dict)]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(r) for r in self.routes], indent=2))

    # --- editing ------------------------------------------------------------

    def get(self, route_id: str) -> Route | None:
        return next((r for r in self.routes if r.id == route_id), None)

    def upsert(self, data: dict) -> tuple[Route | None, str | None]:
        route = Route(**{k: v for k, v in data.items()
                         if k in Route.__dataclass_fields__})
        problem = route.validate()
        if problem:
            return None, problem
        for i, existing in enumerate(self.routes):
            if existing.id == route.id:
                self.routes[i] = route
                break
        else:
            self.routes.append(route)
        self.save()
        return route, None

    def delete(self, route_id: str) -> None:
        # Deleting a route that is walking should stop it walking.
        self.stop(route_id)
        self.routes = [r for r in self.routes if r.id != route_id]
        self.save()

    # --- running ------------------------------------------------------------

    def start(self, route_id: str) -> str | None:
        route = self.get(route_id)
        if route is None:
            return "no such route"
        bots = self.host.bots
        api = self.host.route_api()
        import asyncio
        if api is None:
            return "scripting is disabled"

        steps = route.steps()
        targets = list(route.targets)
        walk, attack = api["walk"], api["attack"]

        async def run() -> None:
            bot = bots.bots[route.name]
            mapper = getattr(self.host.session, "mapper", None)

            # A path is written from one room.  Walked from anywhere else it
            # is fifty steps through the wrong part of the world, so go there
            # first -- and check we arrived, because a route that starts in
            # the wrong place is worse than one that does not start.
            if route.start and mapper is not None:
                if mapper.here != route.start:
                    bot.note = "walking to the start"
                    if not await api["travel"](route.start, route.name):
                        bot.note = "could not reach the start of the path"
                        return
                if mapper.here != route.start:
                    bot.note = "did not reach the start of the path"
                    return

            for command in route.setup_steps():
                # These are not directions, so they cost APM like anything
                # else and go through the queue.
                self.host.session.queue.put(command)
            if route.setup_steps():
                await asyncio.sleep(0.5)      # let the MUD answer first
            while True:
                for step in steps:
                    if not await walk(step):
                        bot.note = f"{step!r} did not go anywhere"
                        return
                    bot.steps += 1
                    room = self.host.session.world.room
                    if route.polite and room.players():
                        # Somebody else is here.  Nobody wants their kill
                        # taken by another player's script, so wait it out
                        # rather than fighting through them.
                        bot.note = "waiting: " + ", ".join(
                            p.name for p in room.players())
                        while room.players():
                            await asyncio.sleep(2.0)
                        bot.note = ""
                    for mob in room.mobs():
                        if wanted(mob, targets):
                            if await attack(mob):
                                bot.kills += 1
                    if route.rest:
                        await asyncio.sleep(route.rest)
                if not route.loop:
                    bot.note = f"finished {len(steps)} steps"
                    return

        bots.start(route.name, run, owner=f"route:{route.id}")
        return None

    def stop(self, route_id: str) -> bool:
        route = self.get(route_id)
        return False if route is None else self.host.bots.stop(route.name)

    def status(self) -> list[dict]:
        running = {b["name"]: b for b in self.host.bots.status()}
        out = []
        for route in self.routes:
            row = asdict(route)
            live = running.get(route.name)
            row["running"] = bool(live and live["running"])
            row["steps_taken"] = live["steps"] if live else 0
            row["kills"] = live["kills"] if live else 0
            row["note"] = live["note"] if live else ""
            row["step_count"] = len(route.steps())
            out.append(row)
        return out
