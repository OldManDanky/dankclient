"""Scripting: registration, dispatch, edge-triggering, aliases, hot reload."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
from mud.lines import LineAssembler, strip_ansi  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.triggers import Trigger, TriggerSet, literal_hint  # noqa: E402


#: What actually left the client, in order.  A single command is sent
#: immediately rather than queued, so tests must look at both.  The list hangs
#: off the session itself -- keying by id() silently shared state between
#: tests, because CPython reuses ids once an object is collected.
def outgoing(session) -> list[str]:
    return session.sent_lines + session.queue.pending


def make(tmp: Path):
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    # Standing in for the socket.  The queue holds anything put while there is
    # nothing to write to, so a fixture that fakes only the send function is
    # one where nothing ever goes out.
    session._writer = object()
    host = ScriptHost(session, tmp)
    return session, host, session.sent_lines


def write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / f"{name}.py"
    path.write_text(body)
    return path


# --- line assembly -----------------------------------------------------------

def test_lines_span_reads():
    a = LineAssembler()
    assert a.feed(b"You are ") == []
    assert a.feed(b"hit!\r\nAgain!\n") == [("You are hit!", "You are hit!"),
                                           ("Again!", "Again!")]
    assert a.partial == ""


def test_ansi_is_stripped_for_matching():
    raw = "\x1b[0;32mShamus\x1b[0m tells you: 'hi'"
    assert strip_ansi(raw) == "Shamus tells you: 'hi'"


# --- prefilter ---------------------------------------------------------------

def test_literal_hint_picks_a_fixed_substring():
    assert literal_hint(r"(?P<who>\w+) has arrived") == "has arrived"
    assert literal_hint(r"^\d+$") is None
    assert literal_hint(r"You are hit by (.+)") == "You are hit by"


def test_prefilter_skips_regexes_that_cannot_match():
    ts = TriggerSet()
    ts.add(Trigger(r"(?P<who>\w+) has arrived", lambda m: None))
    ts.add(Trigger(r"nothing like this", lambda m: None))
    assert len(ts.candidates("Grot has arrived")) == 1
    assert ts.candidates("unrelated text") == []


def test_contains_and_glob_modes():
    ts = TriggerSet()
    ts.add(Trigger("tells you", lambda m: None, mode="contains"))
    ts.add(Trigger("* tells you: *", lambda m: None, mode="glob"))
    assert len(ts.fire("Grot tells you: 'hi'")) == 2
    assert ts.fire("Grot smiles") == []


# --- scripting ---------------------------------------------------------------

def test_script_registers_and_fires(tmp_path=Path("/tmp/mudscripts1")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    write(tmp_path, "s", "seen = []\n"
                         "@trigger(r'(?P<who>\\w+) has arrived')\n"
                         "def a(m): send('greet ' + m['who'])\n")
    assert host.load(tmp_path / "s.py")
    session.bus.emit(events.LINE, "Grot has arrived", "Grot has arrived")
    assert outgoing(session) == ["greet Grot"]


def test_watches_are_edge_triggered(tmp_path=Path("/tmp/mudscripts2")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    write(tmp_path, "s", "@when(lambda p: p.hp_pct is not None and p.hp_pct < 35)\n"
                         "def panic(): send('flee')\n")
    host.load(tmp_path / "s.py")

    session.world.apply("FFF", "B~100")
    session.world.apply("FFF", "A~90")     # 90% -- fine
    assert outgoing(session) == []

    session.world.apply("FFF", "A~30")     # crossed the threshold
    session.world.apply("FFF", "A~20")     # still below: must NOT fire again
    session.world.apply("FFF", "A~10")
    assert outgoing(session) == ["flee"], "level-triggering would spam"

    session.world.apply("FFF", "A~90")     # recovered
    session.world.apply("FFF", "A~20")     # crossed again -> rearmed
    assert outgoing(session) == ["flee", "flee"]


def test_aliases_intercept_typed_input(tmp_path=Path("/tmp/mudscripts3")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    write(tmp_path, "s", "@alias(r'^k (?P<t>.+)$')\n"
                         "def k(m): send('kill ' + m['t'])\n")
    host.load(tmp_path / "s.py")
    assert host.input("k orc") is True
    assert outgoing(session) == ["kill orc"]
    assert host.input("say hello") is False      # falls through to the MUD


def test_reload_unwinds_the_old_hooks(tmp_path=Path("/tmp/mudscripts4")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    path = write(tmp_path, "s", "@trigger('ping')\ndef a(m): send('one')\n")
    host.load(path)
    session.bus.emit(events.LINE, "ping", "ping")
    assert outgoing(session) == ["one"]
    sent.clear()
    session.queue.flush()

    time.sleep(0.01)
    path.write_text("@trigger('ping')\ndef a(m): send('two')\n")
    assert host.reload_changed() == ["s"]
    session.bus.emit(events.LINE, "ping", "ping")
    assert outgoing(session) == ["two"], "old handler still registered"


def test_a_broken_script_does_not_take_the_client_down(tmp_path=Path("/tmp/mudscripts5")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    write(tmp_path, "bad", "this is not valid python <<<\n")
    assert host.load(tmp_path / "bad.py") is False
    assert "bad" in host.errors

    write(tmp_path, "good", "@trigger('ok')\ndef a(m): send('fine')\n")
    host.load(tmp_path / "good.py")
    session.bus.emit(events.LINE, "ok", "ok")
    assert outgoing(session) == ["fine"]


def test_a_raising_handler_is_reported_not_fatal(tmp_path=Path("/tmp/mudscripts6")):
    tmp_path.mkdir(exist_ok=True)
    session, host, sent = make(tmp_path)
    write(tmp_path, "s",
          "@trigger('boom')\ndef a(m): raise ValueError('nope')\n"
          "@trigger('boom')\ndef b(m): send('still ran')\n")
    host.load(tmp_path / "s.py")
    session.bus.emit(events.LINE, "boom", "boom")     # must not raise
    assert outgoing(session) == ["still ran"]


def test_async_handlers_can_await_the_round(tmp_path=Path("/tmp/mudscripts7")):
    tmp_path.mkdir(exist_ok=True)

    async def scenario():
        session, host, sent = make(tmp_path)
        session.clock.period = 0.02
        write(tmp_path, "s",
              "@trigger('go')\n"
              "async def a(m):\n"
              "    send('first')\n"
              "    await tick()\n"
              "    send('second')\n")
        host.load(tmp_path / "s.py")
        session.bus.emit(events.LINE, "go", "go")
        await asyncio.sleep(0.15)
        return outgoing(session)

    assert asyncio.run(scenario()) == ["first", "second"]


def test_glob_captures_its_wildcards():
    """Real lines from a 3k.org capture.  Note the trailing period: without
    matching it explicitly the capture is 'Sandalphon.' and any command built
    from it is wrong."""
    line = "Player dealt the killing blow to Sandalphon."

    loose = Trigger("Player dealt the killing blow to *", lambda m: None, mode="glob")
    assert loose.match(line) == {1: "Sandalphon."}

    tight = Trigger("Player dealt the killing blow to *.", lambda m: None, mode="glob")
    assert tight.match(line) == {1: "Sandalphon"}

    both = Trigger("* dealt the killing blow to *.", lambda m: None, mode="glob")
    assert both.match(line) == {1: "Player", 2: "Sandalphon"}

    # the prefilter must be the fixed middle, not one of the wildcards
    assert both.literal == "dealt the killing blow to"


def test_glob_trailing_star_is_greedy():
    """A non-greedy trailing group would match the empty string."""
    t = Trigger("You say: *", lambda m: None, mode="glob")
    assert t.match("You say: hello there") == {1: "hello there"}


def test_command_mode_is_built_for_aliases():
    """An alias is a verb you type.  `contains` would fire on any line holding
    the word and gives no way to reach the arguments."""
    t = Trigger("gk", lambda m: None, mode="command")

    assert t.match("gk") == {"args": ""}
    assert t.match("gk orc") == {"args": "orc", 1: "orc"}
    assert t.match("GK a big orc") == {"args": "a big orc", 1: "a", 2: "big", 3: "orc"}

    # the failures that make `contains` wrong for this
    assert t.match("xgk") is None
    assert t.match("gkk") is None
    assert t.match("say gk please") is None
