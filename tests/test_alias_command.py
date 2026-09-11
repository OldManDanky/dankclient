"""/alias: an alias made from the input line, as tt++'s #alias does.

    /alias gk kill {1};glance      two commands, the first word after it as {1}
    /alias                         the ones there are
    /unalias gk                    gone

It is an ordinary alias rule, so it is kept with the character, is in
Options -> Aliases, and behaves exactly like one made there.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
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


def typed(session, host, text):
    said = []
    commands.handle(text, session, host, said.append)
    return said


def test_an_alias_made_from_the_input_line_works_like_any_other():
    session, host, store = make()
    said = typed(session, host, "/alias gk kill {1};glance")
    assert said[0] == "new alias gk: kill {1} ; glance", said
    assert host.input("gk rat")
    assert out(session) == ["kill rat", "glance"]
    rule = store.rules[0]
    assert (rule.kind, rule.mode, rule.pattern, rule.name) == ("alias", "command", "gk", "gk")


def test_args_is_everything_after_the_word():
    session, host, store = make()
    typed(session, host, "/alias ct ctell {args}")
    assert host.input("ct back in five")
    assert out(session) == ["ctell back in five"]


def test_it_is_kept_with_the_character():
    session, host, store = make()
    typed(session, host, "/alias gk kill {1}")
    again = RuleStore(host, store.path)
    again.load()
    assert [(r.pattern, r.actions) for r in again.rules] == [
        ("gk", [{"type": "send", "text": "kill {1}"}])]


def test_setting_it_again_changes_it_and_keeps_its_group():
    session, host, store = make()
    typed(session, host, "/alias gk kill {1}")
    store.upsert({**store.rules[0].__dict__, "group": "solo"})
    said = typed(session, host, "/alias GK bash {1}")
    assert said[0] == "changed alias gk: bash {1}", said
    assert len(store.rules) == 1
    assert store.rules[0].group == "solo"
    assert host.input("gk rat") and out(session) == ["bash rat"]


def test_listing_showing_and_removing():
    session, host, store = make()
    typed(session, host, "/alias gk kill {1};glance")
    typed(session, host, "/alias ct ctell {args}")
    listing = typed(session, host, "/alias")[0]
    assert listing.index("ct") < listing.index("gk"), "in order"
    assert "kill {1} ; glance" in listing
    assert "kill {1} ; glance" in typed(session, host, "/alias gk")[0]
    assert typed(session, host, "/unalias gk") == ["removed the alias gk"]
    assert not host.input("gk rat")
    assert "no alias 'gk'" in typed(session, host, "/unalias gk")[0]
    s2, h2, _ = make()
    assert "no aliases" in typed(s2, h2, "/alias")[0]


def test_a_wait_can_go_between_the_commands():
    async def go():
        session, host, store = make()
        typed(session, host, "/alias loot kill rat;/wait 0.05;get all")
        assert store.rules[0].actions[1] == {"type": "wait", "text": "0.05"}
        assert host.input("loot")
        assert out(session) == ["kill rat"]
        await asyncio.sleep(0.1)
        assert out(session) == ["kill rat", "get all"]
    asyncio.run(go())


def test_a_mode_can_be_made_from_the_input_line():
    session, host, store = make()
    store.upsert({"kind": "trigger", "pattern": "arrives", "group": "party",
                  "enabled": False, "actions": [{"type": "send", "text": "follow leader"}]})
    typed(session, host, "/alias partymode /group party on")
    assert host.input("partymode")
    assert out(session) == [], "the / command is the client's"
    assert store.rules[0].enabled


def test_what_it_refuses():
    session, host, store = make()
    assert "cannot start with /" in typed(session, host, "/alias /x look")[0]
    assert "wait" in typed(session, host, "/alias x look;/wait soon;n")[0]
    assert "nothing after it" in typed(session, host, "/alias x look;/wait 2")[0]
    assert not store.rules


def test_ksolo_switches_the_party_group_off():
    """Asked for in so many words: `/alias ksolo /group party off`."""
    session, host, store = make()
    store.upsert({"kind": "trigger", "pattern": "arrives", "group": "party",
                  "actions": [{"type": "send", "text": "follow leader"}]})
    store.upsert({"kind": "trigger", "pattern": "arrives", "group": "solo",
                  "enabled": False, "actions": [{"type": "send", "text": "kill it"}]})
    typed(session, host, "/alias ksolo /group party off")
    assert host.input("ksolo")
    assert [r.enabled for r in store.rules if r.kind == "trigger"] == [False, False]
    typed(session, host, "/alias ksolo /group party off;/group solo on")
    assert host.input("ksolo")
    assert [r.enabled for r in store.rules if r.kind == "trigger"] == [False, True]
    host._on_line("A rat arrives.", "A rat arrives.")
    assert out(session) == ["kill it"]


def test_the_list_is_by_group():
    session, host, store = make()
    typed(session, host, "/alias ksolo /group party off")
    typed(session, host, "/alias kparty /group party on")
    typed(session, host, "/alias gk kill {1}")
    for word in ("ksolo", "kparty"):
        rule = next(r for r in store.rules if r.pattern == word)
        store.upsert({**rule.__dict__, "group": "modes"})
    lines = typed(session, host, "/alias")[0].splitlines()
    assert lines[0] == "modes:" and "kparty" in lines[1] and "ksolo" in lines[2], lines
    assert lines[3] == "no group:" and "gk" in lines[4], lines
    assert "(group modes)" in typed(session, host, "/alias ksolo")[0]
