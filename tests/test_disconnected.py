"""Disconnect for the night, and the night does not go out on reconnect.

Reported after a real session: disconnected on purpose before bed, and while
there was no socket the timers kept their beat -- the game clock free-runs at
two seconds when there is no signal to lock onto -- and every command they
produced was kept, because `put` holds what it cannot send.  86 of them were
still waiting in the morning.  `/flush` dropped them; nothing else would have.

Two things were wrong, and both are fixed here:

* a timer has no business firing when there is no connection.  The beat is
  the game's, and with no socket there is no game;
* the queue must not keep for later what has lost its moment.  It is the
  same rule the deadman already follows -- "twenty stale commands going out
  the moment somebody comes back is the opposite of the point" -- and it now
  applies to a line that has sat in the heap longer than the APM budget's own
  minute, however it got there.

A blip still works: a rule that fires while the socket is away for a second
or two goes out when it comes back.  That is worth keeping, and is what the
holding was written for.
"""

from __future__ import annotations

import asyncio
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.outbound import SendQueue  # noqa: E402
from mud.session import Session  # noqa: E402


class Fake:
    """A clock the test winds by hand, for both the beat and the stopwatch.

    `wait` gives out a fixed number of beats and then cancels, which is how a
    test drives the real drain loop to a standstill rather than a stand-in.
    """

    def __init__(self) -> None:
        self.now = 1000.0
        self.left = 0

    def __call__(self) -> float:
        return self.now

    async def wait(self) -> None:
        if self.left <= 0:
            raise asyncio.CancelledError
        self.left -= 1
        self.now += 2.0                # the game's beat
        await asyncio.sleep(0)


def queue(clock: Fake, ready):
    sent: list[str] = []
    q = SendQueue(sent.append, clock, ready=ready, per_tick=3)
    q._now = clock                     # the stale stopwatch, wound by the test
    return q, sent


def drain(q, beats: int) -> None:
    """Run the queue's own loop for so many beats."""
    q._clock.left = beats

    async def go() -> None:
        try:
            await q.run()
        except asyncio.CancelledError:
            pass
    asyncio.new_event_loop().run_until_complete(go())


# --- the queue ---------------------------------------------------------------

def test_a_nights_worth_of_timers_does_not_go_out_on_reconnect():
    clock = Fake()
    live = [False]
    q, sent = queue(clock, lambda: live[0])
    for _ in range(86):                    # what was actually found waiting
        q.put("xp")
        clock.now += 290.0                 # a timer every 290s, all night
    assert len(q) == 86, "it is still kept while there is nowhere to send it"
    live[0] = True
    drain(q, 60)
    assert sent == [], f"{len(sent)} stale command(s) went out"
    assert len(q) == 0


def test_a_blip_still_delivers():
    clock = Fake()
    live = [False]
    q, sent = queue(clock, lambda: live[0])
    q.put("kill rat")
    clock.now += 3.0                       # back in three seconds
    live[0] = True
    drain(q, 1)
    assert sent == ["kill rat"]


def test_the_line_that_went_stale_goes_and_the_fresh_one_stays():
    clock = Fake()
    q, sent = queue(clock, lambda: True)
    q.put("xp", pace="round")              # ROUND is always queued
    clock.now += 300.0
    q.put("score", pace="round")
    drain(q, 1)
    assert sent == ["score"], sent


# --- the timers --------------------------------------------------------------

def with_a_timer():
    """A session whose only rule is a timer, due every beat."""
    from mud import events
    from mud.rules import Rule, RuleStore
    from mud.scripts import ScriptHost
    s = Session(jumpstart=False, sec_code=1,
                prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    s.mip_seen = True
    host = ScriptHost(s, "/nonexistent")
    host.rules = RuleStore(host, "/nonexistent/rules.json")
    host.rules.rules = [Rule(kind="timer", name="xp", every=290,
                             actions=[{"type": "send", "text": "xp"}])]
    host.rules.register()
    # Anything under MIN_EVERY is refused at registration, and a harness with
    # no timer in it would pass the test below by having nothing to fire.
    assert host.rules._timers, "the timer was not registered"
    return s, host, events


def asked_for(s) -> int:
    """Commands the timer produced, whether they went out or are waiting."""
    return len(s.queue) + s.queue.sent


def test_a_timer_does_not_fire_when_there_is_no_connection():
    s, host, events = with_a_timer()
    s._writer, s.connected = None, False
    for pair in host.rules._timers:
        pair[1] = time.monotonic() - 1.0   # overdue
    for _ in range(20):
        s.bus.emit(events.TICK)
    assert asked_for(s) == 0, f"a timer fired {asked_for(s)} time(s) with no socket"


def test_a_timer_fires_again_once_the_socket_is_back():
    s, host, events = with_a_timer()
    s._writer, s.connected = Wire(), True
    for pair in host.rules._timers:
        pair[1] = time.monotonic() - 1.0
    s.bus.emit(events.TICK)
    assert asked_for(s) > 0, "the timer never fired at all"


class Wire:
    def write(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


def test_the_client_says_what_it_threw_away():
    """Silently dropping them is its own puzzle -- "my ticks stopped working"."""
    from mud import events
    s = Session(jumpstart=False, sec_code=1,
                prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    said: list[bytes] = []
    s.bus.on(events.TEXT, said.append)
    s.queue._now = lambda: time.monotonic() - 300.0   # everything is an age old
    s.queue.put("xp", pace="round")
    s.queue._now = time.monotonic
    assert s.queue.drop_stale() == 1
    assert b"dropped 1 queued command(s)" in b"".join(said), said
