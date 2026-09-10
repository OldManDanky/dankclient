"""The deadman: once nobody has typed for a while, nothing automated goes out.

Fifteen minutes by default.  Bots pause where they are and carry on when a
command is typed; triggers, timers and script sends are dropped rather than
saved up for later.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import patrol  # noqa: E402
from mud.deadman import Deadman  # noqa: E402
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
    d = Deadman(15, clock=clock)
    clock.now = 14 * 60 + 59
    assert not d.tripped
    clock.now = 15 * 60
    assert d.tripped


def test_a_typed_command_lets_go_and_starts_the_count_again():
    clock = Clock()
    changes: list[bool] = []
    d = Deadman(15, clock=clock, on_change=changes.append)
    clock.now = 16 * 60
    assert d.tripped
    d.touched()
    assert not d.tripped and changes == [True, False]
    clock.now = 16 * 60 + 14 * 60
    assert not d.tripped


def test_zero_is_off():
    clock = Clock()
    d = Deadman(0, clock=clock)
    clock.now = 10 ** 6
    assert not d.tripped


def test_switching_it_off_while_tripped_lets_go_at_once():
    clock = Clock()
    d = Deadman(15, clock=clock)
    clock.now = 20 * 60
    assert d.tripped
    d.set_minutes(0)
    assert not d.tripped


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


# --- the setting ---------------------------------------------------------------

def test_the_default_is_fifteen_minutes():
    s, _, _ = session()
    assert s.deadman.minutes == 15


def test_the_setting_is_kept_with_the_map():
    store = Store()
    s, _, _ = session(store)
    WebServer(s)._on_client_message(b'{"t": "deadman", "minutes": 30}')
    assert store.setting("deadman:minutes") == "30"
    assert Session(store=store, prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json")
                   ).deadman.minutes == 30


def test_the_page_is_told_and_has_the_setting():
    s, _, clock = session()
    clock.now = 15 * 60
    assert WebServer(s).snapshot()["deadman"] == {"minutes": 15.0, "tripped": True}
    html = (UI / "index.html").read_text()
    for part in ('id="deadman-min"', 'id="deadman-note"', 'id="deadman-why"'):
        assert part in html, part
    assert "t: 'deadman', minutes: n" in (UI / "app.js").read_text()
