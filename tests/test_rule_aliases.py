"""A rule's send goes out as typing it would: through your aliases, and safely.

A tester asked whether a client alias works from a trigger; it did not -- the
trigger sent the alias's word to 3K.  Now it does, with a limit on aliases
calling aliases and a stop for a rule firing so fast it can only be a loop.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, rules  # noqa: E402
from mud.lines import strip_ansi  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402


def make(tmp):
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    session._writer = object()
    session.shown = []
    session.bus.on(events.TEXT, lambda d: session.shown.append(strip_ansi(d.decode("latin-1"))))
    host = ScriptHost(session, Path(tmp) / "scripts")
    store = RuleStore(host, Path(tmp) / "rules.json")
    host.rules = store
    return session, host, store


def add(store, **rule):
    made, problem = store.upsert(rule)
    assert made is not None, problem
    store.register()
    return made


def sent(session):
    return session.sent_lines + session.queue.pending


def line(session, text):
    session.bus.emit(events.LINE, text, text)


def screen(session):
    return "".join(session.shown)


def test_a_trigger_that_sends_a_client_alias_runs_the_alias():
    with tempfile.TemporaryDirectory() as tmp:
        session, host, store = make(tmp)
        add(store, kind="alias", mode="command", pattern="gk",
            actions=[{"type": "send", "text": "kill {1}"}, {"type": "send", "text": "glance"}])
        add(store, kind="trigger", mode="contains", pattern="arrives",
            actions=[{"type": "send", "text": "gk rat"}])
        line(session, "A rat arrives.")
        assert sent(session) == ["kill rat", "glance"]


def test_a_send_splits_on_semicolons_and_a_backslash_sends_it_as_written():
    with tempfile.TemporaryDirectory() as tmp:
        session, host, store = make(tmp)
        add(store, kind="alias", mode="command", pattern="gk",
            actions=[{"type": "send", "text": "kill {1}"}])
        add(store, kind="trigger", mode="contains", pattern="arrives",
            actions=[{"type": "send", "text": "gk rat;bow"},
                     {"type": "send", "text": "\\gk rat;n"}])
        line(session, "A rat arrives.")
        assert sent(session) == ["kill rat", "bow", "gk rat;n"]


def test_an_alias_that_calls_itself_stops_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        session, host, store = make(tmp)
        add(store, kind="alias", mode="command", pattern="again",
            actions=[{"type": "send", "text": "again"}])
        add(store, kind="trigger", mode="contains", pattern="go round",
            actions=[{"type": "send", "text": "again"}])
        line(session, "go round")
        assert sent(session) == [], "nothing reaches 3K from a loop of aliases"
        assert screen(session).count(f"{rules.MOST_DEPTH} deep") == 1
        line(session, "go round")
        assert screen(session).count(f"{rules.MOST_DEPTH} deep") == 2, "said again for a new chain"


def test_a_rule_firing_like_a_loop_is_switched_off_until_it_is_saved_again():
    with tempfile.TemporaryDirectory() as tmp:
        session, host, store = make(tmp)
        rule = add(store, kind="trigger", mode="contains", pattern="ping", name="echo",
                   actions=[{"type": "send", "text": "pong"}])
        for _ in range(rules.STORM_FIRES + 10):
            line(session, "ping")
        assert len(sent(session)) == rules.STORM_FIRES
        assert screen(session).count("looks like a loop") == 1
        assert "echo: fired more than" in screen(session)

        session.sent_lines.clear()
        store.upsert({**rule.__dict__})
        store.register()
        line(session, "ping")
        assert sent(session) == ["pong"], "saved again, it answers again"


def test_a_line_no_alias_takes_still_goes_to_3k():
    with tempfile.TemporaryDirectory() as tmp:
        session, host, store = make(tmp)
        add(store, kind="alias", mode="command", pattern="gk",
            actions=[{"type": "send", "text": "kill {1}"}])
        add(store, kind="trigger", mode="contains", pattern="arrives",
            actions=[{"type": "send", "text": "bow {0}"}, {"type": "send", "text": "gkx rat"}])
        line(session, "A rat arrives.")
        assert sent(session) == ["bow {0}", "gkx rat"]
