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
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import set_aside, write_atomically
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


def _route(raw) -> Route | None:
    """One saved route, or None if it cannot be one.

    As with rules: a key from a newer version is dropped, not a reason to
    refuse to start, and one broken route does not take the others with it.
    """
    if not isinstance(raw, dict):
        return None
    try:
        route = Route(**{k: v for k, v in raw.items()
                         if k in Route.__dataclass_fields__})
        route.steps()
        route.setup_steps()
    except (TypeError, ValueError, AttributeError):
        return None
    return route


class RouteStore:
    def __init__(self, host, path: str | Path = "scripts/routes.json") -> None:
        self.host = host                      # ScriptHost, for its Bots
        self.path = Path(path)
        self.routes: list[Route] = []
        #: route id -> where it was paused: the step it had reached, the room
        #: that left it in, and its counts.  Kept on disk, so a pause survives
        #: closing the client.
        self.paused: dict[str, dict] = {}

    @property
    def paused_path(self) -> Path:
        return self.path.with_name(self.path.stem + "-paused.json")

    # --- persistence --------------------------------------------------------

    def load(self) -> None:
        self._load_paused()
        if not self.path.exists():
            self.routes = []
            return
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, list):
                raise ValueError("not a list of routes")
        except (ValueError, OSError):
            set_aside(self.path)         # kept, not overwritten by the next save
            self.routes = []
            return
        self.routes = [r for r in map(_route, raw) if r is not None]

    def _load_paused(self) -> None:
        self.paused = {}
        if not self.paused_path.exists():
            return
        try:
            raw = json.loads(self.paused_path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("not a set of pauses")
        except (ValueError, OSError):
            set_aside(self.paused_path)
            return
        self.paused = {k: v for k, v in raw.items() if isinstance(v, dict)}

    def _save_paused(self) -> None:
        write_atomically(self.paused_path, json.dumps(self.paused, indent=2))

    def save(self) -> None:
        write_atomically(self.path,
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
                # A new path makes "step 12" mean some other step.
                if existing.steps() != route.steps() and self.paused.pop(route.id, None):
                    self._save_paused()
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

    def start(self, route_id: str, resume: bool = False) -> str | None:
        """Walk a route from the top -- or, resuming, from where it paused."""
        route = self.get(route_id)
        if route is None:
            return "no such route"
        bots = self.host.bots
        api = self.host.route_api()
        import asyncio
        if api is None:
            return "scripting is disabled"

        # Starting again forgets a pause, and resuming uses it up.  A pause
        # taken before the first step is only a start.
        back = self.paused.pop(route.id, None)
        if back is not None:
            self._save_paused()
        if not resume or not back or not (back.get("step") or back.get("steps")):
            back = None

        steps = route.steps()
        targets = list(route.targets)
        walk, attack = api["walk"], api["attack"]

        async def in_room(bot) -> None:
            """What the route does in each room it arrives in."""
            room = self.host.session.world.room
            if route.polite and room.players():
                # Somebody else is here.  Nobody wants their kill taken by
                # another player's script, so wait it out rather than
                # fighting through them.
                bot.note = "waiting: " + ", ".join(p.name for p in room.players())
                while room.players():
                    await asyncio.sleep(2.0)
                bot.note = ""
            for mob in room.mobs():
                if wanted(mob, targets):
                    if await attack(mob):
                        bot.kills += 1
            if route.rest:
                await asyncio.sleep(route.rest)

        async def run() -> None:
            bot = bots.bots[route.name]
            mapper = getattr(self.host.session, "mapper", None)
            first = 0

            if back is not None:
                bot.steps, bot.kills = back.get("steps", 0), back.get("kills", 0)
                first = min(int(back.get("step", 0)), len(steps))
                where = back.get("room")
                # Set before walking back, so pausing on the way back keeps
                # the same place rather than a new one halfway there.
                bot.at, bot.room = first, where
                if where and mapper is not None and mapper.here != where:
                    bot.note = "walking back to where it paused"
                    if (not await api["travel"](where, route.name)
                            or mapper.here != where):
                        # Kept: Resume can be tried again from nearer.
                        self.paused[route.id] = back
                        self._save_paused()
                        bot.note = "could not get back to where it paused"
                        return
                bot.note = ""
                # The route was in this room when it stopped, so it does what
                # it does in a room -- the creature it came for may be back.
                await in_room(bot)
            else:
                # A path is written from one room.  Walked from anywhere else
                # it is fifty steps through the wrong part of the world, so go
                # there first -- and check we arrived, because a route that
                # starts in the wrong place is worse than one that does not.
                if route.start and mapper is not None:
                    if mapper.here != route.start:
                        bot.note = "walking to the start"
                        if not await api["travel"](route.start, route.name):
                            bot.note = "could not reach the start of the path"
                            return
                    if mapper.here != route.start:
                        bot.note = "did not reach the start of the path"
                        return
                    bot.note = ""

                for command in route.setup_steps():
                    # These are not directions, so they cost APM like anything
                    # else and go through the queue.
                    self.host.session.queue.put(command)
                if route.setup_steps():
                    await asyncio.sleep(0.5)      # let the MUD answer first

            while True:
                for i in range(first, len(steps)):
                    step = steps[i]
                    if not await walk(step):
                        bot.note = f"{step!r} did not go anywhere"
                        return
                    bot.steps += 1
                    bot.at = i + 1
                    bot.room = mapper.here if mapper is not None else None
                    await in_room(bot)
                first = 0
                if not route.loop:
                    bot.note = f"finished {len(steps)} steps"
                    return

        bots.start(route.name, run, owner=f"route:{route.id}")
        return None

    def pause(self, route_id: str) -> str | None:
        """Stop, and remember where: the step it had reached and the room."""
        route = self.get(route_id)
        if route is None:
            return "no such route"
        bot = self.host.bots.bots.get(route.name)
        if bot is None or not bot.running:
            return "it is not walking"
        self.paused[route.id] = {"step": bot.at, "room": bot.room,
                                 "steps": bot.steps, "kills": bot.kills,
                                 "when": time.strftime("%H:%M")}
        self._save_paused()
        self.host.bots.stop(route.name)
        return None

    def stop(self, route_id: str) -> bool:
        """Stop it, and forget a pause: stopping means not coming back."""
        route = self.get(route_id)
        if route is None:
            return False
        if self.paused.pop(route.id, None) is not None:
            self._save_paused()
        return self.host.bots.stop(route.name)

    def _room_name(self, room) -> str:
        store = getattr(self.host.session, "store", None)
        if not room or store is None:
            return ""
        try:
            row = store.room(room)
        except Exception:
            return ""
        return (row["name"] or "") if row else ""

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
            row["paused"] = None
            held = self.paused.get(route.id)
            if held:
                # Paused, even while its task is still winding down: a cancel
                # lands on the loop's next turn, and the list sent straight
                # back from Pause would otherwise still say it is walking.
                row["running"] = False
                row["paused"] = {"step": held.get("step", 0),
                                 "room": held.get("room"),
                                 "room_name": self._room_name(held.get("room")),
                                 "when": held.get("when", "")}
                row["steps_taken"] = held.get("steps", 0)
                row["kills"] = held.get("kills", 0)
                said = row["note"] if row["note"] not in ("", "stopped") else ""
                row["note"] = (f"paused at step {held.get('step', 0)} of "
                               f"{row['step_count']}" + (f" — {said}" if said else ""))
            out.append(row)
        return out
