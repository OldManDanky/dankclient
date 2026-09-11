"""A wait in a rule's actions: everything below it goes out that much later.

"kill rat", wait 2, "get all": the first at once, the second two seconds on.
The wait hands the rest to the event loop, so nothing else is held up while it
counts, and a rule edited, switched off or deleted meanwhile does not carry on
as it was.  /stop drops whatever is waiting.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands  # noqa: E402
from mud.rules import MOST_WAIT, Rule, RuleStore, describe  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402


def make():
    where = Path(tempfile.mkdtemp())
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    session._writer = object()
    host = ScriptHost(session, where)
    host.notes = []
    host.note = host.notes.append
    store = RuleStore(host, where / "rules.json")
    host.rules = store
    return session, host, store


def out(session) -> list[str]:
    return session.sent_lines + session.queue.pending


def acts(*pairs):
    return [{"type": t, "text": x} for t, x in pairs]


LOOT = acts(("send", "kill rat"), ("wait", "0.05"), ("send", "get all"))


def fire(host, line):
    """A line from the MUD, handed to the triggers the way the client does."""
    host._on_line(line, line)


# --- checking one --------------------------------------------------------------

def test_a_wait_takes_a_number_of_seconds():
    ok = Rule(pattern="x", actions=LOOT)
    assert ok.validate() is None
    for bad in ("soon", "0", "-1", "nan", str(MOST_WAIT + 1)):
        rule = Rule(pattern="x", actions=acts(("wait", bad), ("send", "y")))
        assert rule.validate(), bad
    assert Rule(pattern="x", actions=acts(("wait", str(MOST_WAIT)),
                                          ("send", "y"))).validate() is None


def test_a_wait_with_nothing_after_it_is_refused():
    rule = Rule(pattern="x", actions=acts(("send", "y"), ("wait", "2")))
    assert "nothing after it" in rule.validate()
    rule = Rule(pattern="x", actions=acts(("send", "y"), ("wait", "2"), ("wait", "1")))
    assert "nothing after it" in rule.validate()


def test_listings_say_wait_and_how_long():
    assert describe({"type": "wait", "text": "2.50"}) == "wait 2.5s"
    assert describe({"type": "send", "text": "xp"}) == "xp"


# --- running one ---------------------------------------------------------------

def test_what_comes_after_a_wait_goes_out_later():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        assert out(session) == ["kill rat"], "the first goes at once"
        await asyncio.sleep(0.02)
        assert out(session) == ["kill rat"], "the second waits"
        await asyncio.sleep(0.08)
        assert out(session) == ["kill rat", "get all"]
        assert not store._waiting
    asyncio.run(go())


def test_captures_reach_the_actions_after_a_wait():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "mode": "regex",
                      "pattern": r"(?P<who>\w+) waves",
                      "actions": acts(("wait", "0.02"), ("send", "wave {who}"),
                                      ("log", "waved at {who}"))})
        fire(host, "Friend waves")
        await asyncio.sleep(0.06)
        assert out(session) == ["wave Friend"]
        assert host.notes == ["waved at Friend"]
    asyncio.run(go())


def test_firing_again_while_waiting_runs_both():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        fire(host, "A rat arrives.")
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat", "kill rat", "get all", "get all"]
    asyncio.run(go())


def test_an_alias_can_wait_too():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "alias", "pattern": "there", "mode": "exact",
                      "actions": acts(("send", "n"), ("wait", "0.02"), ("send", "s"))})
        assert host.input("there")
        await asyncio.sleep(0.06)
        assert out(session) == ["n", "s"]
    asyncio.run(go())


# --- stopping one --------------------------------------------------------------

def test_editing_the_rule_drops_what_it_was_waiting_to_do():
    async def go():
        session, host, store = make()
        rule, _ = store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        store.upsert({"id": rule.id, "kind": "trigger", "pattern": "arrives",
                      "actions": acts(("send", "flee"))})
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat"]
    asyncio.run(go())


def test_switching_it_off_or_deleting_it_does_too():
    async def go():
        session, host, store = make()
        rule, _ = store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        store.upsert({"id": rule.id, "kind": "trigger", "pattern": "arrives",
                      "actions": LOOT, "enabled": False})
        other, _ = store.upsert({"kind": "trigger", "pattern": "leaves", "actions": LOOT})
        fire(host, "A rat leaves.")
        store.delete(other.id)
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat", "kill rat"]
    asyncio.run(go())


def test_editing_another_rule_leaves_it_waiting():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        store.upsert({"kind": "trigger", "pattern": "unrelated",
                      "actions": acts(("send", "x"))})
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat", "get all"]
    asyncio.run(go())


def test_slash_stop_drops_waiting_rules_and_stops_bots():
    """/stop used to be taken by /flush's branch: it emptied the queue and
    left every bot walking."""
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        stopped = []
        host.bots.stop_all = lambda: stopped.append(True) or 1
        said = []
        assert commands.handle("/stop", session, host, said.append)
        await asyncio.sleep(0.1)
        assert stopped, "the bots were not stopped"
        assert "1 bot(s)" in said[0] and "1 waiting rule(s) dropped" in said[0], said
        assert out(session) == ["kill rat"]
    asyncio.run(go())


def test_the_deadman_holds_what_a_wait_lets_out():
    async def go():
        session, host, store = make()
        store.upsert({"kind": "trigger", "pattern": "arrives", "actions": LOOT})
        fire(host, "A rat arrives.")
        session.queue.held = lambda: True
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat"]
    asyncio.run(go())


# --- as a script -----------------------------------------------------------------

def test_as_a_script_a_wait_is_an_await():
    rule = Rule(kind="trigger", name="loot", pattern="arrives", mode="contains",
                actions=LOOT)
    code = rule.as_python()
    assert "async def loot(m):" in code and "await wait(0.05)" in code, code

    async def go():
        session, host, store = make()
        script = Path(tempfile.mkdtemp()) / "loot.py"
        script.write_text(code)
        assert host.load(script), host.errors
        fire(host, "A rat arrives.")
        await asyncio.sleep(0.02)
        assert out(session) == ["kill rat"]
        await asyncio.sleep(0.08)
        assert out(session) == ["kill rat", "get all"]
    asyncio.run(go())
