"""Bus, clock and send-queue behaviour."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, outbound  # noqa: E402
from mud.clock import Clock  # noqa: E402
from mud.events import Bus  # noqa: E402


def test_bus_delivers_and_unsubscribes():
    bus = Bus()
    seen = []
    fn = bus.on(events.TELL, lambda t: seen.append(t))
    bus.emit(events.TELL, "a")
    bus.off(events.TELL, fn)
    bus.emit(events.TELL, "b")
    assert seen == ["a"]


def test_bus_decorator_form():
    bus = Bus()
    seen = []

    @bus.on(events.ROUND)
    def _(n):
        seen.append(n)

    bus.emit(events.ROUND, 3)
    assert seen == [3]


def test_a_raising_handler_cannot_stop_the_others():
    """One bad script must not take the client down."""
    bus = Bus()
    seen = []
    bus.on(events.TEXT, lambda d: (_ for _ in ()).throw(ValueError("boom")))
    bus.on(events.TEXT, lambda d: seen.append(d))
    bus.emit(events.TEXT, b"hello")     # must not raise
    assert seen == [b"hello"]


def test_clock_locks_onto_an_observed_beat():
    c = Clock(period=2.0)
    assert c.source == "free"
    c.observe("round")
    assert c.source == "round" and c.ticks == 1


def test_clock_free_runs_when_the_signal_stops():
    async def scenario():
        c = Clock(period=0.05)          # compressed for the test
        c.observe("regen")
        await c.wait()                  # nothing else observed -> free-run
        return c.source, c.ticks

    source, ticks = asyncio.run(scenario())
    assert source == "free" and ticks == 2


def q(sent, *, soft=80, limit=100, exits=(), period=2.0):
    from mud.outbound import APMMeter, SendQueue
    meter = APMMeter(limit=limit, soft=soft)
    return SendQueue(sent.append, Clock(period=period), apm=meter,
                     exits=lambda: exits)


# --- the governor is actions per minute, not the combat round ---------------
#
# 3k.org watches non-directional commands per minute and takes an interest
# above 100.  That is 1.67/second; one command per 2s round would be 30/min.
# Pacing to the round was three times stricter than the actual rule.

def test_a_single_command_goes_out_at_once():
    sent = []
    q(sent).put("get corpse")
    assert sent == ["get corpse"]


def test_movement_does_not_count_against_the_budget():
    sent = []
    queue = q(sent, exits=("omp", "vortex"))
    for cmd in ("n", "south", "up", "omp", "vortex", "enter"):
        queue.put(cmd)
    assert sent == ["n", "south", "up", "omp", "vortex", "enter"]
    assert queue.apm.rate() == 0, "walking must be free"


def test_named_room_exits_are_movement_too():
    """DDD tells us the exits here, so "omp" is free in a room that has it."""
    from mud.outbound import APMMeter
    m = APMMeter()
    assert m.is_directional("omp", exits=["omp", "n"]) is True
    assert m.is_directional("omp", exits=["n"]) is False
    assert m.is_directional("kill orc", exits=["n"]) is False


def test_it_throttles_only_as_the_minute_fills():
    sent = []
    queue = q(sent, soft=5)
    for i in range(5):
        queue.put(f"cmd {i}")
    assert sent == [f"cmd {i}" for i in range(5)]     # under budget: immediate
    assert queue.apm.headroom() == 0

    queue.put("one too many")
    assert "one too many" not in sent
    assert queue.pending == ["one too many"]


def test_typed_commands_go_out_but_still_count():
    """The budget is about the MUD's view, not about who typed it."""
    sent = []
    queue = q(sent, soft=1)
    queue.now("kill orc")
    assert sent == ["kill orc"]
    assert queue.apm.rate() == 1
    queue.put("scripted")                 # budget spent -> queued
    assert queue.pending == ["scripted"]


def test_now_ignores_the_budget():
    sent = []
    queue = q(sent, soft=0)
    queue.put("urgent", pace=outbound.NOW)
    assert sent == ["urgent"]


def test_panic_ignores_the_budget():
    sent = []
    queue = q(sent, soft=0)
    queue.put("quaff heal", outbound.PANIC)
    assert sent == ["quaff heal"]


def test_panic_can_be_governed_when_asked():
    sent = []
    queue = q(sent, soft=0)
    queue.panic_immediate = False
    queue.put("quaff heal", outbound.PANIC)
    assert sent == [] and queue.pending == ["quaff heal"]


def test_round_pace_always_waits_for_the_beat():
    """Attack rotations want the round even with budget to spare."""
    sent = []
    queue = q(sent)
    queue.put("bash", pace=outbound.ROUND)
    assert sent == []
    assert queue.pending == ["bash"]


def test_priority_orders_the_backlog():
    sent = []
    queue = q(sent, soft=0)
    queue.put("walk north")
    queue.put("walk east")
    queue.put("cast shield", outbound.HIGH)
    assert queue.pending == ["cast shield", "walk north", "walk east"]


def test_order_is_preserved_once_anything_is_queued():
    """A later command must not overtake a queued one just because the budget
    recovered in between."""
    sent = []
    queue = q(sent, soft=1)
    queue.put("one")                      # immediate
    queue.put("two")                      # budget gone -> queued
    queue.apm.soft = 80                   # budget recovers
    queue.put("three")                    # queue non-empty -> still behind two
    assert sent == ["one"]
    assert queue.pending == ["two", "three"]


def test_backlog_drains_on_the_tick():
    async def scenario():
        sent = []
        queue = q(sent, soft=0, period=0.02)
        queue.put("a"); queue.put("b")
        queue.apm.soft = 80               # budget frees up
        queue.start()
        await asyncio.sleep(0.15)
        queue.stop()
        return sent

    assert asyncio.run(scenario()) == ["a", "b"]


def test_flush_is_the_panic_button():
    sent = []
    queue = q(sent, soft=0)
    for i in range(5):
        queue.put(f"cmd {i}")
    assert queue.flush() == 5
    assert len(queue) == 0 and queue.dropped == 5


def test_the_window_rolls():
    from mud.outbound import APMMeter
    m = APMMeter(window=0.05)
    m.record("kill orc")
    assert m.rate() == 1
    import time as _t
    _t.sleep(0.06)
    assert m.rate() == 0


# --- nothing goes out while there is nothing to send it down ------------------

def test_a_command_with_no_socket_waits_rather_than_raising():
    """A rule that fires on a disconnect reaches the queue, and the queue used
    to hand it straight to send(), which raises when there is no writer. The
    rule looked broken rather than pending -- and coming back is exactly when
    "send this" should happen."""
    from mud.outbound import NOW

    sent, up = [], {"yes": False}
    queue = q(sent)
    queue.ready = lambda: up["yes"]

    queue.put("say I fell over")
    queue.put("flee", pace=NOW)          # not even an immediate one goes
    assert sent == []
    assert len(queue) == 2


def test_what_waited_goes_out_in_order_once_there_is_a_socket():
    async def scenario():
        sent, up = [], {"yes": False}
        queue = q(sent, period=0.01)
        queue.ready = lambda: up["yes"]
        queue.put("first")
        queue.put("second")

        up["yes"] = True
        queue.start()
        await asyncio.sleep(0.2)
        queue.stop()
        return sent

    assert asyncio.run(scenario())[:2] == ["first", "second"]


def test_the_drain_will_not_empty_the_queue_into_a_dead_socket():
    """The beat keeps coming while the connection is down, and a drain that
    only checked the clock would hand every held command to a writer that is
    not there."""
    async def scenario():
        sent, up = [], {"yes": False}
        queue = q(sent, period=0.01)
        queue.ready = lambda: up["yes"]
        for n in range(6):
            queue.put(f"cmd{n}")
        queue.start()
        await asyncio.sleep(0.1)          # several beats, all with no socket
        held = len(queue)
        queue.stop()
        return sent, held

    sent, held = asyncio.run(scenario())
    assert sent == [], "it sent into a dead socket"
    assert held == 6, "and it must still have them for when one turns up"
