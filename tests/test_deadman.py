"""The deadman: once nobody has typed for a while, nothing automated goes out.

Fifteen minutes by default, shorter if set, never longer; 0 is off.  Steppers
pause where they are and carry on when a command is typed; timers are dropped
rather than saved up for later.  Triggers still answer, but never with a move.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, patrol  # noqa: E402
from mud.deadman import Deadman  # noqa: E402
from mud.outbound import answering  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.web import WebServer  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Wire:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        pass


def session(store=None):
    s = Session(jumpstart=False, store=store,
                prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    wire = Wire()
    s._writer, s.connected = wire, True
    clock = Clock()
    s.deadman._clock, s.deadman._last = clock, 0.0
    return s, wire, clock


def sent(wire: Wire) -> list[str]:
    return [b.decode().strip() for b in wire.sent]


# --- the switch itself ---------------------------------------------------------

def test_it_trips_on_time_and_not_before():
    clock = Clock()
    d = Deadman(clock=clock)
    clock.now = 14 * 60 + 59
    assert not d.tripped
    clock.now = 15 * 60
    assert d.tripped


def test_a_typed_command_lets_go_and_starts_the_count_again():
    clock = Clock()
    changes: list[bool] = []
    d = Deadman(clock=clock, on_change=changes.append)
    clock.now = 16 * 60
    assert d.tripped
    d.touched()
    assert not d.tripped and changes == [True, False]
    clock.now = 16 * 60 + 14 * 60
    assert not d.tripped


def test_it_can_be_shorter_or_off_but_never_longer():
    """3K's rule is fifteen minutes: the most.  0 is off."""
    clock = Clock()
    d = Deadman(clock=clock)
    assert d.set_minutes(5) == 5
    clock.now = 5 * 60
    assert d.tripped
    for asked, kept in ((0, 0), ("0", 0), (-3, 15), (60, 15), (1440, 15),
                        (0.2, 1), ("ten", 15), (None, 15), (float("nan"), 15),
                        (float("inf"), 15), ("7", 7)):
        assert d.set_minutes(asked) == kept, asked
    assert Deadman(90, clock=clock).minutes == 15
    clock.now = 10 ** 6
    assert d.tripped


def test_zero_is_off():
    clock = Clock()
    d = Deadman(0, clock=clock)
    clock.now = 10 ** 6
    assert not d.tripped


def test_switching_it_off_while_tripped_lets_go_at_once():
    clock = Clock()
    changes: list[bool] = []
    d = Deadman(clock=clock, on_change=changes.append)
    clock.now = 20 * 60
    assert d.tripped
    d.set_minutes(0)
    assert not d.tripped and changes == [True, False]


def test_made_longer_while_tripped_it_lets_go():
    clock = Clock()
    changes: list[bool] = []
    d = Deadman(5, clock=clock, on_change=changes.append)
    clock.now = 6 * 60
    assert d.tripped
    d.set_minutes(10)
    assert not d.tripped and changes == [True, False]
    clock.now = 10 * 60
    assert d.tripped


# --- what it holds back ------------------------------------------------------

def test_nothing_automated_goes_out_while_tripped():
    s, wire, clock = session()
    clock.now = 15 * 60
    s.queue.put("xp")                 # a timer, a trigger
    s.queue.auto_now("flee")          # a script's send_now
    assert sent(wire) == []


def test_what_was_waiting_is_dropped_not_saved_for_later():
    s, wire, clock = session()
    s._writer = None                  # nothing to send down: it waits
    s.queue.put("xp")
    s.queue.put("score")
    assert len(s.queue) == 2
    s._writer = wire
    clock.now = 15 * 60
    assert s.deadman.tripped
    assert len(s.queue) == 0


def test_a_command_typed_on_the_page_goes_out_and_lets_go():
    s, wire, clock = session()
    web = WebServer(s)
    clock.now = 20 * 60
    assert s.deadman.tripped
    web._on_client_message(b'{"t": "cmd", "d": "look"}')
    assert not s.deadman.tripped
    assert sent(wire) == ["look"]
    s.queue.put("xp")                 # and automation works again
    assert sent(wire) == ["look", "xp"]


def test_a_bot_pauses_where_it_is_and_carries_on():
    """Paused, not stopped: a route picks up from the step it was on."""
    async def go():
        s, wire, clock = session()
        api = patrol.make_api(s, s.bots, "test")
        clock.now = 15 * 60
        step = asyncio.ensure_future(api["walk"]("n", 0.2))
        await asyncio.sleep(0.05)
        paused = sent(wire)
        s.deadman.touched()
        await asyncio.sleep(0.05)
        carried_on = sent(wire)
        step.cancel()
        return paused, carried_on

    paused, carried_on = asyncio.run(go())
    assert paused == []
    assert carried_on == ["n"]


# --- what still answers --------------------------------------------------------

def rules_for(s: Session) -> RuleStore:
    folder = Path(tempfile.mkdtemp())
    host = ScriptHost(s, folder)
    store = RuleStore(host, folder / "rules.json")
    host.rules = store
    return store


def test_a_trigger_still_answers_what_3k_says_while_tripped():
    """Stepping, the deadman trips mid-fight: the corpse trigger still fires."""
    s, wire, clock = session()
    store = rules_for(s)
    for pattern, reply in (("You killed", "disperse corpse"), ("Obvious exits", "n")):
        _, err = store.upsert({"kind": "trigger", "pattern": pattern, "mode": "contains",
                               "actions": [{"type": "send", "text": reply}]})
        assert err is None
    clock.now = 15 * 60
    assert s.deadman.tripped
    s.bus.emit(events.LINE, "You killed a rat.", "You killed a rat.")
    s.bus.emit(events.LINE, "Obvious exits: n, s", "Obvious exits: n, s")
    assert sent(wire) == ["disperse corpse"], "an answer goes, a move does not"


def test_only_answers_that_are_not_moves_get_past_it():
    s, wire, clock = session()
    clock.now = 15 * 60
    with answering():
        s.queue.put("disperse corpse")
        s.queue.put("north")
        s.queue.auto_now("n")
        s.queue.auto_now("quaff heal")
    s.queue.put("xp")                 # a timer
    s.queue.auto_now("score")         # a script on its own
    assert sent(wire) == ["disperse corpse", "quaff heal"]


def test_an_answer_waiting_in_the_queue_is_kept_when_it_trips():
    s, wire, clock = session()
    s._writer = None                  # nothing to send down: it waits
    with answering():
        s.queue.put("disperse corpse")
        s.queue.put("s")
    s.queue.put("xp")
    s._writer = wire
    clock.now = 15 * 60
    assert s.deadman.tripped
    assert s.queue.pending == ["disperse corpse"]
    s.queue.drain_once()
    assert sent(wire) == ["disperse corpse"]


def test_a_stepper_started_by_a_trigger_is_still_held():
    """A trigger that starts a path or /go does not make the walk an answer."""
    async def go():
        s, wire, clock = session()
        clock.now = 15 * 60

        async def hunt():
            s.queue.put("get all")
            s.queue.put("kill rat")

        with answering():
            bot = s.bots.start("hunt", hunt, "test")
        await bot.task
        return sent(wire)

    assert asyncio.run(go()) == []


# --- the setting ---------------------------------------------------------------

def test_the_default_is_fifteen_minutes():
    s, _, _ = session()
    assert s.deadman.minutes == 15


def reopened(store: Store) -> Session:
    return Session(store=store, prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))


def test_the_setting_is_kept_with_the_map():
    store = Store()
    s, _, _ = session(store)
    WebServer(s)._on_client_message(b'{"t": "deadman", "minutes": 5}')
    assert s.deadman.minutes == 5
    assert store.setting("deadman:minutes") == "5"
    assert reopened(store).deadman.minutes == 5


def test_the_page_can_turn_it_off_and_it_stays_off():
    store = Store()
    s, _, _ = session(store)
    WebServer(s)._on_client_message(b'{"t": "deadman", "minutes": 0}')
    assert s.deadman.minutes == 0
    assert store.setting("deadman:minutes") == "0"
    assert reopened(store).deadman.minutes == 0


def test_the_page_cannot_make_it_longer():
    store = Store()
    s, _, _ = session(store)
    for asked in (b"30", b"-1", b'"off"', b"null"):
        s.deadman.set_minutes(5)
        WebServer(s)._on_client_message(b'{"t": "deadman", "minutes": ' + asked + b"}")
        assert s.deadman.minutes == 15, asked
        assert store.setting("deadman:minutes") == "15", asked


def test_a_time_an_older_client_saved_is_kept_to_fifteen():
    """Before 0.2.21 it went to a day: past fifteen reads as fifteen, 0 is off."""
    for saved, kept in (("0", 0), ("1440", 15), ("30", 15), ("10", 10), ("", 15)):
        store = Store()
        store.set_setting("deadman:minutes", saved)
        assert reopened(store).deadman.minutes == kept, saved


def test_the_page_is_told_and_has_the_setting():
    s, _, clock = session()
    clock.now = 15 * 60
    assert WebServer(s).snapshot()["deadman"] == {"minutes": 15.0, "tripped": True}
    html = (UI / "index.html").read_text()
    for part in ('id="deadman-note"', 'id="deadman-why"', 'id="deadman-rule"',
                 'id="deadman-min" type="number" min="0" max="15"'):
        assert part in html, part
    assert "or 0 for off" in " ".join(html.split())
    js = (UI / "app.js").read_text()
    assert "t: 'deadman', minutes: n" in js
    assert "Math.min(15, typed)" in js


def test_the_session_panel_is_told_how_long_you_have_been_idle():
    """Right after mudlag: seconds since you typed, not since 3K last heard a stepper."""
    s, _, clock = session()
    web = WebServer(s)
    clock.now = 125
    chrome = web.snapshot()["chrome"]
    keys = list(chrome)
    assert keys[keys.index("mudlag") + 1] == "idle", keys
    assert chrome["idle"] == 125
    s.queue.put("xp")                 # a timer: you are no less idle
    assert web.snapshot()["chrome"]["idle"] == 125
    web._on_client_message(b'{"t": "cmd", "d": "look"}')
    assert web.snapshot()["chrome"]["idle"] == 0
