"""GUI-managed triggers and aliases.

Most 3K players are not programmers -- Portal knew that, which is why Actions,
Alias and CreateNewEvent were all dialogs.  These rules are plain data, edited
in the UI and stored as JSON, but they register into exactly the same
TriggerSet that scripts use, so there is one execution model and one place
where matching happens.

`as_python()` renders any rule as the equivalent script, which is the second
door: click your way to something that works, then take the code and grow it.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .outbound import NOW, PACED, PACES, ROUND
from .triggers import Trigger


def context_fields(world) -> dict[str, object]:
    """State every rule can reach, regardless of what fired it."""
    p = world.player
    out = {f: getattr(p, f, None) for f in CONTEXT_FIELDS
           if f not in ("round", "room")}
    out["round"] = p.__dict__.get("round")
    out["room"] = world.room.short
    return out


def payload_fields(event: str, payload) -> dict[str, object]:
    """Flatten an event payload into the names an action can interpolate."""
    if event == "round":
        return {"round": payload}
    if event == "enemy":
        return {"enemy": payload}
    if event == "mip":
        return {"code": getattr(payload, "code", ""),
                "data": getattr(payload, "data", "")}
    if event == "room":
        return {
            "short": getattr(payload, "short", ""),
            "exits": " ".join(getattr(payload, "exits", ()) or ()),
            "mobs": ", ".join(o.name for o in payload.mobs()) if payload else "",
            "players": ", ".join(o.name for o in payload.players()) if payload else "",
            "items": ", ".join(o.name for o in payload.items()) if payload else "",
        }
    if hasattr(payload, "__dataclass_fields__"):
        return {f: getattr(payload, f) for f in payload.__dataclass_fields__}
    return {"value": payload}


def compare(left, op: str, right: str) -> bool:
    if op in ("lt", "lte", "gt", "gte"):
        try:
            a, b = float(left), float(right)
        except (TypeError, ValueError):
            return False
        return {"lt": a < b, "lte": a <= b, "gt": a > b, "gte": a >= b}[op]
    text = "" if left is None else str(left)
    if op == "eq":
        return text.lower() == right.lower()
    if op == "ne":
        return text.lower() != right.lower()
    if op == "contains":
        return right.lower() in text.lower()
    if op == "matches":
        try:
            return re.search(right, text) is not None
        except re.error:
            return False
    return False

OWNER = "gui"          # so reload can unwind exactly these

MODES = ("command", "contains", "glob", "regex")

#: A timer is checked on the game's own beat, so anything under one beat is a
#: number the client cannot keep.  3k.org runs on two seconds.
MIN_EVERY = 2.0

#: What a rule reacts to.
KINDS = ("trigger", "alias", "event", "watch", "timer")

#: MIP events a rule may hook, with the fields their payload exposes.
#: Available to every rule, whatever fired it -- MIP is already tracking these,
#: so a tell rule can report your health and a round rule can name the target.
CONTEXT_FIELDS = ("hp", "max_hp", "hp_pct", "sp", "sp_pct",
                  "gp1", "gp2", "enemy", "enemy_pct", "round", "room")

EVENT_FIELDS = {
    "tell": ("who", "message", "from_me"),
    "chat": ("channel", "who", "message", "command"),
    "round": ("round",),
    "enemy": ("enemy",),
    "room": ("short", "exits", "mobs", "players", "items"),
    "mip": ("code", "data"),
}

#: Numbers a watch can compare against.  All come from MIP, so none are scraped.
WATCH_FIELDS = ("hp", "max_hp", "hp_pct", "sp", "max_sp", "sp_pct",
                "gp1", "max_gp1", "gp2", "max_gp2",
                "enemy", "enemy_pct", "round")

OPS = {
    "lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
    "eq": "is", "ne": "is not", "contains": "contains", "matches": "matches",
}
#: how quickly the actions reach the MUD
PACE_LABELS = {
    NOW: "immediate (ignores the APM budget)",
    PACED: "normal (throttles near the APM limit)",
    ROUND: "one per combat round",
}
ACTIONS = ("send", "log")


def _safe_format(text: str, captured: dict) -> str:
    """Substitute {name} from captures, leaving unknown braces alone."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in captured:
            return str(captured[key])
        if key.isdigit() and int(key) in captured:
            return str(captured[int(key)])
        return m.group(0)

    return re.sub(r"\{(\w+)\}", repl, text)


@dataclass
class Rule:
    id: str = ""
    kind: str = "trigger"          # "trigger" | "alias"
    name: str = ""
    pattern: str = ""
    mode: str = "contains"
    actions: list[dict[str, str]] = field(default_factory=list)
    enabled: bool = True
    priority: int = 0
    stop: bool = False
    pace: str = PACED
    #: kind == "event"
    event: str = "tell"
    conditions: list[dict[str, str]] = field(default_factory=list)
    #: kind == "watch"
    watch_field: str = "hp_pct"
    op: str = "lt"
    value: str = ""
    edge: bool = True
    #: kind == "timer" -- seconds between firings
    every: float = 60.0

    def __post_init__(self) -> None:
        if self.pace not in PACES:
            self.pace = PACED
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if self.mode not in MODES:
            self.mode = "contains"
        if self.kind not in KINDS:
            self.kind = "trigger"

    def validate(self) -> str | None:
        if self.kind == "event":
            if self.event not in EVENT_FIELDS:
                return f"unknown event {self.event!r}"
            for c in self.conditions:
                if c.get("op") == "matches":
                    try:
                        re.compile(c.get("value", ""))
                    except re.error as exc:
                        return f"bad regex in condition: {exc}"
        elif self.kind == "timer":
            try:
                every = float(self.every)
            except (TypeError, ValueError):
                return f"{self.every!r} is not a number of seconds"
            if every < MIN_EVERY:
                return (f"every {every:g}s is faster than the game beat -- "
                        f"{MIN_EVERY:g}s is the shortest that means anything")
        elif self.kind == "watch":
            if self.watch_field not in WATCH_FIELDS:
                return f"unknown field {self.watch_field!r}"
            if self.op not in OPS:
                return f"unknown comparison {self.op!r}"
            if not str(self.value).strip():
                return "no value to compare against"
            if self.op in ("lt", "lte", "gt", "gte"):
                if self.watch_field == "enemy":
                    return "enemy is a name -- compare it with is / contains"
                try:
                    float(self.value)
                except ValueError:
                    return f"{self.value!r} is not a number"
        elif not self.pattern.strip():
            return "pattern is empty"
        elif self.mode == "regex":
            try:
                re.compile(self.pattern)
            except re.error as exc:
                return f"bad regex: {exc}"
        if not self.actions:
            return "no actions"
        for a in self.actions:
            if a.get("type") not in ACTIONS:
                return f"unknown action {a.get('type')!r}"
            if not str(a.get("text", "")).strip():
                return "an action has no text"
        return None

    def as_python(self) -> str:
        name = re.sub(r"\W+", "_", self.name or self.pattern or self.event
                      or self.watch_field)[:30].strip("_") or "rule"
        pace_arg = "" if self.pace == PACED else f", pace={self.pace!r}"

        body = []
        for a in self.actions:
            text = a["text"].replace('"', '\\"')
            # captures arrive as the dict `m`, so {who} has to become {m['who']}
            text = re.sub(r"\{(\w+)\}", lambda mo: "{m[" + repr(mo.group(1)) + "]}",
                          text)
            if a["type"] == "send":
                body.append(f'    send(f"{text}"{pace_arg})')
            else:
                body.append(f'    log(f"{text}")')
        block = "\n".join(body) or "    pass"

        if self.kind == "event":
            guards = []
            for c in self.conditions:
                guards.append(f'    # only when {c.get("field")} '
                              f'{OPS.get(c.get("op", ""), c.get("op"))} '
                              f'{c.get("value")!r}')
            head = "\n".join(guards)
            return (f"@on({self.event!r})\n"
                    f"def {name}(m):\n"
                    + (head + "\n" if head else "") + block + "\n")

        if self.kind == "timer":
            return (f"@every({float(self.every):g})\n"
                    f"def {name}(m=None):\n" + block.replace("m[", "_[") + "\n")

        if self.kind == "watch":
            sym = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
                   "eq": "==", "ne": "!="}.get(self.op, "==")
            field_expr = (f"p.{self.watch_field}" if self.watch_field != "round"
                          else "p.__dict__.get('round')")
            edge = "" if self.edge else ", edge=False"
            return (f"@when(lambda p: {field_expr} is not None "
                    f"and {field_expr} {sym} {self.value}{edge})\n"
                    f"def {name}():\n"
                    + block.replace("m[", "player_field[") + "\n")

        deco = "alias" if self.kind == "alias" else "trigger"
        args = [repr(self.pattern)]
        if self.mode != "regex":
            args.append(f"mode={self.mode!r}")
        if self.priority:
            args.append(f"priority={self.priority}")
        if self.stop:
            args.append("stop=True")
        return (f"@{deco}({', '.join(args)})\n"
                f"def {name}(m):\n" + block + "\n")


class RuleStore:
    def __init__(self, host, path: str | Path = "scripts/rules.json") -> None:
        self.host = host                      # ScriptHost
        self.path = Path(path)
        self.rules: list[Rule] = []
        self._subs: list[tuple[str, object]] = []
        self._watches: list[list] = []
        self._timers: list[list] = []          # [rule, next_at]
        self._state_hooked = False
        self._tick_hooked = False

    # --- persistence --------------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            self.rules = []
            return
        try:
            raw = json.loads(self.path.read_text())
        except (ValueError, OSError):
            self.rules = []
            return
        self.rules = [Rule(**r) for r in raw if isinstance(r, dict)]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(r) for r in self.rules], indent=2))

    # --- registration -------------------------------------------------------

    def register(self) -> None:
        """Re-register every enabled rule, replacing what was there."""
        from . import events

        self.host.triggers.remove_owner(OWNER)
        self.host.aliases.remove_owner(OWNER)
        for kind, fn in self._subs:
            self.host.bus.off(kind, fn)
        self._subs.clear()
        self._watches.clear()
        self._timers.clear()

        for rule in self.rules:
            if not rule.enabled or rule.validate():
                continue

            if rule.kind in ("trigger", "alias"):
                target = (self.host.aliases if rule.kind == "alias"
                          else self.host.triggers)
                target.add(Trigger(rule.pattern, self._runner(rule), rule.mode,
                                   OWNER, rule.priority, rule.stop))

            elif rule.kind == "event":
                handler = self._event_handler(rule)
                self.host.bus.on(rule.event, handler)
                self._subs.append((rule.event, handler))

            elif rule.kind == "watch":
                self._watches.append([rule, False])      # [rule, last_state]

            elif rule.kind == "timer":
                # Due immediately would fire every timer at once on a reload,
                # which for a reload you did not mean is a burst of commands
                # you did not mean either.  One period from now.
                self._timers.append([rule, time.monotonic() + float(rule.every)])

        if self._watches and not self._state_hooked:
            self.host.bus.on(events.STATE, self._on_state)
            self._state_hooked = True
        if self._timers and not self._tick_hooked:
            self.host.bus.on(events.TICK, self._on_tick)
            self._tick_hooked = True

    def _on_tick(self) -> None:
        """Fire whatever is due.

        On the game's own beat rather than a timer of our own, so a tick keeps
        the MUD's time rather than the wall's.  Nothing fires before MIP is
        flowing: the beat free-runs when there is no signal to lock onto, and
        that includes sitting at the login prompt, where sending "xp" every
        290 seconds types it into the password box.
        """
        if not getattr(self.host.session, "mip_seen", False):
            return
        now = time.monotonic()
        for pair in self._timers:
            rule, due = pair
            if now < due:
                continue
            pair[1] = now + float(rule.every)
            self._runner(rule)(context_fields(self.host.session.world))

    def _event_handler(self, rule: Rule):
        run = self._runner(rule)

        def handle(*args) -> None:
            payload = args[0] if len(args) == 1 else args
            fields = context_fields(self.host.session.world)
            # the event's own fields win, so {enemy} on an enemy rule is the
            # value that just arrived rather than whatever state has caught up to
            fields.update(payload_fields(rule.event, payload))
            for cond in rule.conditions:
                if not compare(fields.get(cond.get("field", "")),
                               cond.get("op", "contains"),
                               str(cond.get("value", ""))):
                    return
            run(fields)

        return handle

    def _on_state(self, name: str, new, old) -> None:
        """Watches are edge-triggered: they fire on the crossing, not while.

        Level-triggered, "hp below 35" fires on every composite you are under
        it -- and 3k.org sends two per combat round.
        """
        player = self.host.session.world.player
        for entry in self._watches:
            rule, was = entry
            left = self._read(player, rule.watch_field)
            now = left is not None and compare(left, rule.op, str(rule.value))
            entry[1] = now
            if now and (not was or not rule.edge):
                self._runner(rule)(self._player_fields(player))

    @staticmethod
    def _read(player, field_name: str):
        if field_name == "round":
            return player.__dict__.get("round")
        return getattr(player, field_name, None)

    def _player_fields(self, player) -> dict[str, object]:
        return context_fields(self.host.session.world)

    def _runner(self, rule: Rule):
        session, host = self.host.session, self.host

        def run(captured: dict[str, Any]) -> None:
            for action in rule.actions:
                text = _safe_format(action["text"], captured or {})
                if action["type"] == "send":
                    session.queue.put(text, rule.priority, rule.pace)
                else:
                    host.note(text)

        run.__name__ = re.sub(r"\W+", "_", rule.name or rule.pattern)[:30] or "rule"
        return run

    # --- editing ------------------------------------------------------------

    def upsert(self, data: dict) -> tuple[Rule | None, str | None]:
        data = {k: v for k, v in data.items() if k in Rule.__dataclass_fields__}
        rule = Rule(**data)
        problem = rule.validate()
        if problem:
            return None, problem
        for i, existing in enumerate(self.rules):
            if existing.id == rule.id:
                self.rules[i] = rule
                break
        else:
            self.rules.append(rule)
        self.save()
        self.register()
        return rule, None

    def delete(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        if len(self.rules) == before:
            return False
        self.save()
        self.register()
        return True

    # --- views --------------------------------------------------------------

    def listing(self) -> dict:
        """Editable rules plus read-only ones registered by script files."""
        from_scripts = [
            {"owner": t.owner, "kind": kind, "pattern": t.pattern,
             "mode": t.mode, "literal": t.literal}
            for kind, which in (("trigger", self.host.triggers),
                                ("alias", self.host.aliases))
            for t in which.all() if t.owner != OWNER
        ]
        return {
            "rules": [asdict(r) for r in self.rules],
            "scripts": from_scripts,
            "modes": list(MODES),
            "actions": list(ACTIONS),
            "paces": [{"value": v, "label": l} for v, l in PACE_LABELS.items()],
            "kinds": list(KINDS),
            "events": {k: list(v) for k, v in EVENT_FIELDS.items()},
            "watch_fields": list(WATCH_FIELDS),
            "context_fields": list(CONTEXT_FIELDS),
            "ops": [{"value": v, "label": l} for v, l in OPS.items()],
        }
