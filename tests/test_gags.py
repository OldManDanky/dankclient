"""Gags: lines kept off the screen, the way tt++'s #gag does it.

The screen is fed in network chunks, not lines, so a gag has to hold a line
until it is whole -- and 3K marks no prompts (not one GA or EOR in 59
captures), so an unfinished line is shown after a moment rather than waiting
for an ending that is not coming.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, events  # noqa: E402
from mud.gags import ERASE, LineGate  # noqa: E402
from mud.rules import Rule, RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.triggers import Trigger  # noqa: E402
from mud.web import WebServer  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def gate(*gags: str) -> LineGate:
    return LineGate(lambda plain: any(g in plain for g in gags),
                    active=lambda: bool(gags))


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


# --- the gate ----------------------------------------------------------------

def test_with_no_gags_nothing_is_held():
    """Exactly the stream as it was before gags existed."""
    g = gate()
    assert g.feed(b"one\r\nHP 100> ") == b"one\r\nHP 100> "
    assert not g.pending


def test_a_gagged_line_is_not_drawn():
    assert gate("spam").feed(b"one\r\nbuy spam now\r\ntwo\r\n") == b"one\r\ntwo\r\n"


def test_a_line_that_arrives_in_two_reads_is_judged_whole():
    g = gate("spam")
    assert g.feed(b"one\r\nbuy sp") == b"one\r\n"
    assert g.pending
    assert g.feed(b"am now\r\ntwo\r\n") == b"two\r\n"


def test_a_line_that_is_not_gagged_comes_out_whole():
    g = gate("spam")
    assert g.feed(b"ab") == b""
    assert g.feed(b"c\r\n") == b"abc\r\n"


def test_colour_does_not_hide_a_line_from_its_gag():
    assert gate("You hit").feed(b"\x1b[31mYou\x1b[0m hit it\r\n") == b""


def test_a_prompt_is_shown_when_nothing_more_comes():
    g = gate("spam")
    assert g.feed(b"HP 100> ") == b""
    assert g.release() == b"HP 100> "


def test_a_line_shown_early_is_wiped_when_the_rest_is_gagged():
    """The rest arrived after the wait: take back what is already drawn."""
    g = gate("spam")
    g.feed(b"buy ")
    assert g.release() == b"buy "
    assert g.feed(b"spam now\r\nnext\r\n") == ERASE + b"next\r\n"


def test_a_gagged_prompt_stays_gagged_to_the_end_of_its_line():
    g = gate("HP")
    assert g.feed(b"HP 100> ") == b""
    assert g.release() == b""
    assert g.feed(b"\r\nnext\r\n") == b"next\r\n"


# --- in the session ----------------------------------------------------------

def session(store=None) -> Session:
    return Session(prefixes_path=str(tmp() / "prefixes.json"), store=store)


def test_the_screen_loses_the_line_and_the_rules_do_not():
    """tt++ behaves this way too: gagging a line is not a reason for the
    trigger that reacts to it to stop working."""
    async def go():
        s = session()
        s.gags.add(Trigger("spam", lambda m: None, "contains", "test"))
        shown, lines = [], []
        s.bus.on(events.TEXT, shown.append)
        s.bus.on(events.LINE, lambda raw, plain: lines.append(plain))
        s._consume(b"hello\r\nbuy spam now\r\nHP 100> ")
        early = b"".join(shown)
        await asyncio.sleep(0.3)
        return early, b"".join(shown), lines

    early, later, lines = asyncio.run(go())
    assert early == b"hello\r\n", "the prompt waits a moment for an ending"
    assert later == b"hello\r\nHP 100> ", "and is then shown"
    assert "buy spam now" in lines


def test_without_gags_the_session_holds_nothing_back():
    s = session()
    shown = []
    s.bus.on(events.TEXT, shown.append)
    s._consume(b"hello\r\nHP 100> ")
    assert b"".join(shown) == b"hello\r\nHP 100> "


def test_a_refresh_does_not_put_gagged_lines_back():
    s = session(Store())
    s.logbook.add("recv", "hello")
    s.logbook.add("recv", "buy spam now")
    s.gags.add(Trigger("spam", lambda m: None, "contains", "test"))
    back = WebServer(s)._scrollback()
    texts = [line["text"] for line in back["lines"]]
    assert "hello" in texts and "buy spam now" not in texts


# --- rules, commands and scripts ---------------------------------------------

def host():
    d = tmp()
    s = session()
    h = ScriptHost(s, d / "scripts")
    h.rules = RuleStore(h, d / "rules.json")
    return s, h


def test_a_gag_needs_nothing_else_to_do():
    assert Rule(kind="trigger", pattern="spam", gag=True).validate() is None
    assert Rule(kind="trigger", pattern="spam").validate() == "no actions"


def test_a_gag_rule_gags_and_is_not_a_trigger_with_nothing_to_do():
    s, h = host()
    _, problem = h.rules.upsert(asdict(Rule(kind="trigger", pattern="spam",
                                            mode="contains", gag=True)))
    assert problem is None
    assert s.is_gagged("buy spam now")
    assert len(h.triggers) == 0


def test_a_gag_shows_as_python():
    assert Rule(kind="trigger", pattern="spam", gag=True).as_python() == "gag('spam')\n"
    both = Rule(kind="trigger", pattern="x", mode="regex", gag=True,
                actions=[{"type": "send", "text": "y"}]).as_python()
    assert both.startswith("gag('x', mode='regex')\n@trigger(")


def test_gag_gags_and_ungag_ungags():
    s, h = host()
    said: list[str] = []
    commands.handle("/gag spam", s, h, said.append)
    assert s.is_gagged("buy spam now")
    commands.handle("/gags", s, h, said.append)
    assert "spam" in said[-1]
    commands.handle("/ungag spam", s, h, said.append)
    assert not s.is_gagged("buy spam now")
    assert not h.rules.rules


def test_ungag_leaves_a_trigger_that_does_other_things():
    s, h = host()
    h.rules.upsert(asdict(Rule(kind="trigger", pattern="spam", mode="contains",
                               gag=True, actions=[{"type": "send", "text": "y"}])))
    commands.handle("/ungag spam", s, h, lambda _t: None)
    assert not s.is_gagged("spam") and len(h.rules.rules) == 1
    assert len(h.triggers) == 1


def test_a_script_can_gag_and_takes_it_away_when_it_unloads():
    s, h = host()
    h.dir.mkdir(parents=True)
    path = h.dir / "quiet.py"
    path.write_text('gag("noise")\n')
    h.load(path)
    assert s.is_gagged("more noise")
    h.unload("quiet")
    assert not s.is_gagged("more noise")


# --- the page ----------------------------------------------------------------

def test_the_trigger_form_has_a_gag_box():
    html = (UI / "index.html").read_text()
    js = (UI / "rules.js").read_text()
    assert 'id="f-gag"' in html and "$('f-gag').checked" in js


def test_the_last_command_can_stay_in_the_box():
    html = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    assert 'id="keep-cmd"' in html
    assert "prefs.get('keep-cmd'" in js and "cmd.select()" in js
