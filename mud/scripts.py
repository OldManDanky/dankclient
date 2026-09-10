"""User scripting.

Scripts are ordinary Python files in a directory.  Each is executed with the
API injected as globals, so there is no import boilerplate and every
registration can be attributed to the file that made it -- which is what makes
hot reload possible: reloading a file unwinds exactly its own hooks.

    @on("tell")
    async def helpme(e):
        if "help" in e.message:
            send(f"tell {e.who} omw")

    @when(lambda p: p.hp_pct and p.hp_pct < 35)     # edge-triggered
    async def panic():
        send("flee", PANIC)

    @trigger(r"(?P<who>\\w+) has arrived")
    def arrival(m):
        log(f"{m['who']} showed up")

Handlers may be sync or async.  Async ones can `await tick()` or
`await round_tick()` and are cancellable, which is what the bot layer is built
from.  A handler that raises is reported and the rest still run.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import events, patrol
from .outbound import HIGH, LOW, NORMAL, NOW, PACED, PANIC, ROUND
from .triggers import Trigger, TriggerSet


@dataclass
class Watch:
    """A state predicate.  Edge-triggered: fires on the crossing, not while."""

    pred: Callable[[Any], bool]
    fn: Callable
    owner: str
    edge: bool = True
    last: bool = False


@dataclass
class Periodic:
    seconds: float
    fn: Callable
    owner: str
    next_at: float = 0.0


@dataclass
class Registry:
    """Everything one script file registered, so reload can unwind it."""

    handlers: list[tuple[str, Callable]] = field(default_factory=list)
    watches: list[Watch] = field(default_factory=list)
    periodics: list[Periodic] = field(default_factory=list)
    aliases: list[Trigger] = field(default_factory=list)
    triggers: int = 0


class ScriptHost:
    def __init__(self, session, directory: str | Path = "scripts") -> None:
        self.session = session
        self.bus = session.bus
        self.dir = Path(directory)
        self.triggers = TriggerSet()
        self.aliases = TriggerSet()
        self.registries: dict[str, Registry] = {}
        self.mtimes: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self._current: str = ""
        self._watch_task: asyncio.Task | None = None
        self.rules = None            # RuleStore, attached by the caller
        #: The session's, so a speedwalk started from the map and a hunt
        #: started from a script are the same kind of thing and stop the same
        #: way.  Reloading a script still stops the bots that script started.
        self.bots = session.bots
        self.routes = None           # RouteStore, attached by the caller

        self.bus.on(events.LINE, self._on_line)
        self.bus.on(events.STATE, self._on_state)
        self.bus.on(events.TICK, self._on_tick)

    def route_api(self) -> dict | None:
        """The same primitives a script gets, for routes built in the UI.

        Deliberately the same code path: a route drawn in a form and a route
        written in Python must not be able to behave differently.
        """
        return patrol.make_api(self.session, self.bots, "route")

    # --- lifecycle ----------------------------------------------------------

    def load_all(self) -> None:
        if not self.dir.is_dir():
            return
        for path in sorted(self.dir.glob("*.py")):
            if not path.name.startswith("_"):
                self.load(path)

    def load(self, path: Path) -> bool:
        name = path.stem
        self.unload(name)
        registry = Registry()
        self.registries[name] = registry
        self._current = name
        try:
            code = compile(path.read_text(), str(path), "exec")
            exec(code, self._namespace(name))          # noqa: S102 -- the point
        except Exception:
            self.errors[name] = traceback.format_exc()
            self.unload(name)
            self.note(f"\x1b[31m{name}: failed to load\x1b[0m\n"
                      + self.errors[name])
            return False
        finally:
            self._current = ""
        self.errors.pop(name, None)
        self.mtimes[name] = path.stat().st_mtime
        n = (len(registry.handlers) + len(registry.watches)
             + len(registry.periodics) + registry.triggers + len(registry.aliases))
        self.note(f"{name}: {n} hook(s)")
        return True

    def unload(self, name: str) -> None:
        registry = self.registries.pop(name, None)
        if registry is None:
            return
        for kind, fn in registry.handlers:
            self.bus.off(kind, fn)
        self.triggers.remove_owner(name)
        self.aliases.remove_owner(name)
        gags = getattr(self.session, "gags", None)
        if gags is not None:
            gags.remove_owner(name)
        # A bot outlives the call that started it, so unloading its script
        # must stop it.  Otherwise editing a route leaves the old one still
        # walking, and the two take turns steering.
        for bot in list(self.bots.bots.values()):
            if bot.owner == name:
                self.bots.stop(bot.name)
                self.bots.bots.pop(bot.name, None)

    def reload_changed(self) -> list[str]:
        """Reload files whose mtime moved.  Returns what was reloaded."""
        if not self.dir.is_dir():
            return []
        changed = []
        for path in sorted(self.dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            mtime = path.stat().st_mtime
            if self.mtimes.get(path.stem) != mtime:
                self.load(path)
                changed.append(path.stem)
        for name in list(self.registries):
            if not (self.dir / f"{name}.py").exists():
                self.unload(name)
                changed.append(name)
        # script reloads clear owners wholesale; put the GUI rules back
        if changed and self.rules is not None:
            self.rules.register()
        return changed

    def start(self, interval: float = 1.0) -> None:
        """Watch the scripts directory.  Editing a trigger takes effect at
        once -- no reconnect, no reload command, no losing your session."""
        async def poll() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    self.reload_changed()
                except Exception:
                    self.note("reload failed:\n" + traceback.format_exc())

        self._watch_task = asyncio.ensure_future(poll())

    def stop(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()
            self._watch_task = None

    # --- dispatch -----------------------------------------------------------

    def _on_line(self, raw: str, plain: str) -> None:
        for trig, captured in self.triggers.fire(plain):
            self._call(trig.fn, captured, raw=raw, plain=plain)

    def _on_state(self, name: str, new: Any, old: Any) -> None:
        player = self.session.world.player
        for registry in list(self.registries.values()):
            for watch in registry.watches:
                try:
                    now = bool(watch.pred(player))
                except Exception:
                    now = False           # incomplete state is just "not yet"
                fired = now and (not watch.last or not watch.edge)
                watch.last = now
                if fired:
                    self._call(watch.fn, None)

    def _on_tick(self) -> None:
        now = time.monotonic()
        for registry in list(self.registries.values()):
            for job in registry.periodics:
                if now >= job.next_at:
                    job.next_at = now + job.seconds
                    self._call(job.fn, None)

    def input(self, text: str) -> bool:
        """Offer a typed command to the aliases.  True if one consumed it."""
        for trig, captured in self.aliases.fire(text):
            self._call(trig.fn, captured, raw=text, plain=text)
            return True
        return False

    def _call(self, fn: Callable, captured, **extra) -> None:
        try:
            result = fn(captured) if captured is not None else fn()
        except Exception:
            self.note(f"\x1b[31m{getattr(fn, '__name__', fn)} raised:\x1b[0m\n"
                      + traceback.format_exc())
            return
        if asyncio.iscoroutine(result):
            # Held until it finishes, or the loop may collect it halfway.
            task = events.spawn(result, f"script {getattr(fn, '__name__', fn)}")
            if task is not None:
                task.add_done_callback(self._report)

    def _report(self, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() is None:
            return
        exc = task.exception()
        self.note(f"\x1b[31mscript task failed: {exc!r}\x1b[0m")

    def note(self, text: str) -> None:
        self.bus.emit(events.TEXT,
                      f"\r\n\x1b[33m[script] {text}\x1b[0m\r\n".encode("latin-1",
                                                                      "replace"))

    # --- the API a script sees ---------------------------------------------

    def _namespace(self, owner: str) -> dict:
        session, registry = self.session, self.registries[owner]

        def on(kind: str):
            """Subscribe to a bus event.  Bus handlers receive positional args;
            script handlers take a single payload, so adapt between them."""
            def deco(fn):
                def wrapper(*args):
                    payload = args[0] if len(args) == 1 else (args or None)
                    self._call(fn, payload)
                self.bus.on(kind, wrapper)
                registry.handlers.append((kind, wrapper))
                return fn
            return deco

        def when(pred, edge: bool = True):
            def deco(fn):
                registry.watches.append(Watch(pred, fn, owner, edge))
                return fn
            return deco

        def trigger(pattern: str, mode: str = "regex", priority: int = 0,
                    stop: bool = False):
            def deco(fn):
                self.triggers.add(Trigger(pattern, fn, mode, owner, priority, stop))
                registry.triggers += 1
                return fn
            return deco

        def alias(pattern: str, mode: str = "regex"):
            def deco(fn):
                self.aliases.add(Trigger(pattern, fn, mode, owner))
                return fn
            return deco

        def every(seconds: float):
            def deco(fn):
                registry.periodics.append(Periodic(seconds, fn, owner))
                return fn
            return deco

        def gag(pattern: str, mode: str = "contains"):
            """Keep lines matching this off the screen, as tt++'s #gag does.
            Triggers and the log still see them."""
            session.gags.add(Trigger(pattern, lambda _m=None: None, mode, owner))

        async def tick():
            await session.clock.wait()

        async def round_tick():
            """Wait for the combat round counter to advance."""
            start = session.world.player.__dict__.get("round")
            while True:
                await session.clock.wait()
                if session.world.player.__dict__.get("round") != start:
                    return

        return {
            "__name__": f"script.{owner}",
            "on": on, "when": when, "trigger": trigger, "alias": alias,
            "every": every, "tick": tick, "round_tick": round_tick,
            "gag": gag,
            # send() is paced by a token bucket: a single command goes out at
            # once, a burst falls back to the game tick.
            "send": (lambda text, priority=NORMAL, pace=PACED:
                     session.queue.put(text, priority, pace)),
            # A script is not a person: its "now" is still held by the deadman.
            "send_now": lambda text: session.queue.auto_now(text),
            "send_round": (lambda text, priority=NORMAL:
                           session.queue.put(text, priority, ROUND)),
            "flush": lambda: session.queue.flush(),
            "log": lambda *a: self.note(" ".join(str(x) for x in a)),
            "world": session.world,
            "player": session.world.player,
            "room": session.world.room,
            "session": session,
            "PANIC": PANIC, "HIGH": HIGH, "NORMAL": NORMAL, "LOW": LOW,
            "NOW": NOW, "PACED": PACED, "ROUND": ROUND,
            # walk / attack / arrive / bot / patrol / stop_bots
            **patrol.make_api(session, self.bots, owner),
        }
