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


# --- APM is counted and told, never waited for -----------------------------
#
# 3k.org watches non-directional commands per minute, above 100.  The client
# once held automated commands back near that; 3K's admins would rather the
# player simply knew.  What still waits is the round, and a missing socket.

def test_a_single_command_goes_out_at_once():
    sent = []
    q(sent).put("get corpse")
    assert sent == ["get corpse"]


def test_movement_does_not_count():
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


def test_it_never_holds_anything_back_for_apm():
    """Past the limit, it still goes at once: the player is told, not slowed."""
    sent = []
    queue = q(sent, soft=2, limit=3)
    for i in range(6):
        queue.put(f"cmd {i}")
    assert sent == [f"cmd {i}" for i in range(6)]
    assert queue.pending == [] and queue.apm.rate() == 6


def test_typed_and_automated_commands_both_count():
    """The count is 3K's view of it, not who typed what."""
    sent = []
    queue = q(sent)
    queue.now("kill orc")
    queue.put("scripted")
    assert sent == ["kill orc", "scripted"] and queue.apm.rate() == 2


def test_reaching_the_limit_says_so_once_until_the_minute_calms_down():
    from mud.outbound import APMMeter
    told = []
    meter = APMMeter(limit=3, soft=2, on_over=told.append)
    for i in range(5):
        meter.record(f"cmd {i}")
    assert told == [3], "once, at the crossing -- not once a command past it"
    meter.record("n")
    assert told == [3], "movement never counts"
    meter._stamps.clear()                 # the minute passes
    meter.rate()
    for i in range(3):
        meter.record(f"again {i}")
    assert told == [3, 3], "and again, after it dropped back under soft"


def test_the_session_prints_the_warning():
    from mud import events
    from mud.session import Session
    s = Session("127.0.0.1", 1, sec_code=1)
    said = []
    s.bus.on(events.TEXT, said.append)
    s.apm.limit, s.apm.soft = 2, 1
    s.apm.record("kill orc")
    assert not said
    s.apm.record("kill orc")
    text = b"".join(said).decode("latin-1")
    assert "[client] APM: 2 commands in the last minute" in text, text


def test_now_goes_at_once():
    sent = []
    queue = q(sent)
    queue.put("urgent", pace=outbound.NOW)
    assert sent == ["urgent"]


def test_panic_goes_ahead_of_anything_waiting():
    sent = []
    queue = q(sent)
    queue.put("bash", pace=outbound.ROUND)
    queue.put("quaff heal", outbound.PANIC)
    assert sent == ["quaff heal"] and queue.pending == ["bash"]


def test_panic_can_wait_its_turn_when_asked():
    sent = []
    queue = q(sent)
    queue.panic_immediate = False
    queue.put("bash", pace=outbound.ROUND)
    queue.put("quaff heal", outbound.PANIC)
    assert sent == [] and queue.pending == ["quaff heal", "bash"]


def test_round_pace_always_waits_for_the_beat():
    """Attack rotations want the round, whatever else is going on."""
    sent = []
    queue = q(sent)
    queue.put("bash", pace=outbound.ROUND)
    assert sent == []
    assert queue.pending == ["bash"]


def test_priority_orders_the_backlog():
    sent = []
    queue = q(sent)
    queue.put("bash", pace=outbound.ROUND)    # something waiting
    queue.put("walk north")
    queue.put("walk east")
    queue.put("cast shield", outbound.HIGH)
    assert queue.pending == ["cast shield", "bash", "walk north", "walk east"]


def test_order_is_preserved_once_anything_is_queued():
    """A later command must not overtake one already waiting."""
    sent = []
    queue = q(sent)
    queue.put("one")                      # immediate
    queue.put("two", pace=outbound.ROUND) # waits for the round
    queue.put("three")                    # queue non-empty -> behind two
    assert sent == ["one"]
    assert queue.pending == ["two", "three"]


def test_backlog_drains_on_the_tick():
    async def scenario():
        sent = []
        queue = q(sent, period=0.02)
        queue.put("a", pace=outbound.ROUND); queue.put("b")
        queue.start()
        await asyncio.sleep(0.15)
        queue.stop()
        return sent

    assert asyncio.run(scenario()) == ["a", "b"]


def test_flush_is_the_panic_button():
    sent = []
    queue = q(sent)
    for i in range(5):
        queue.put(f"cmd {i}", pace=outbound.ROUND)    # waiting for the round
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
