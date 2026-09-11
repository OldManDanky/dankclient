"""Groups: rules switched on and off together, from the input line.

A group is a name on each rule.  `/group party on` switches on every rule in
it, `/group solo off` every rule in that one, and an alias whose actions are
those two commands is a "partymode" -- which works because an action that
starts with "/" does what typing it would, instead of going to 3K.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands  # noqa: E402
from mud.rules import Rule, RuleStore  # noqa: E402
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


def fire(host, line):
    host._on_line(line, line)


def typed(session, host, text):
    said = []
    commands.handle(text, session, host, said.append)
    return said


def two_modes(store):
    store.upsert({"kind": "trigger", "pattern": "arrives", "group": "party",
                  "actions": [{"type": "send", "text": "follow leader"}]})
    store.upsert({"kind": "trigger", "pattern": "arrives", "group": "solo",
                  "enabled": False,
                  "actions": [{"type": "send", "text": "kill it"}]})


def test_a_group_is_switched_off_and_on_from_the_input_line():
    session, host, store = make()
    two_modes(store)
    fire(host, "A rat arrives.")
    assert out(session) == ["follow leader"]
    said = typed(session, host, "/group party off")
    assert said == ["party: 1 rule(s) off"]
    fire(host, "A rat arrives.")
    assert out(session) == ["follow leader"], "switched off, it no longer fires"
    typed(session, host, "/group PARTY on")          # whatever the case
    fire(host, "A rat arrives.")
    assert out(session) == ["follow leader", "follow leader"]


def test_an_alias_can_be_a_mode():
    session, host, store = make()
    two_modes(store)
    store.upsert({"kind": "alias", "pattern": "solomode", "mode": "exact",
                  "actions": [{"type": "send", "text": "/group party off"},
                              {"type": "send", "text": "/group solo on"}]})
    store.upsert({"kind": "alias", "pattern": "partymode", "mode": "exact",
                  "actions": [{"type": "send", "text": "/group solo off"},
                              {"type": "send", "text": "/group party on"}]})
    assert host.input("solomode")
    assert out(session) == [], "a / action is the client's, never sent to 3K"
    fire(host, "A rat arrives.")
    assert out(session) == ["kill it"]
    assert host.input("partymode")
    fire(host, "A rat arrives.")
    assert out(session) == ["kill it", "follow leader"]
    assert host.notes[-2:] == ["solo: 1 rule(s) off", "party: 1 rule(s) on"]


def test_the_switch_is_kept():
    session, host, store = make()
    two_modes(store)
    typed(session, host, "/group solo on")
    again = RuleStore(host, store.path)
    again.load()
    assert {r.group: r.enabled for r in again.rules} == {"party": True, "solo": True}


def test_groups_lists_them_and_says_how_many_are_on():
    session, host, store = make()
    two_modes(store)
    store.upsert({"kind": "alias", "pattern": "x", "group": "party", "enabled": False,
                  "actions": [{"type": "send", "text": "y"}]})
    said = typed(session, host, "/groups")[0]
    assert "party" in said and "1 of 2 on" in said
    assert "solo" in said and "off" in said
    shown = typed(session, host, "/group party")[0]
    assert shown.startswith("party: 1 of 2 on"), shown
    assert "trigger" in shown and "arrives" in shown and "follow leader" in shown
    assert "alias" in shown and "off" in shown.splitlines()[2]


def test_a_group_nobody_has_says_which_there_are():
    session, host, store = make()
    two_modes(store)
    said = typed(session, host, "/group raid on")[0]
    assert "no rules in a group called 'raid'" in said and "party, solo" in said
    session, host, store = make()
    assert "no groups" in typed(session, host, "/groups")[0]


def test_a_group_name_is_tidied_and_kept_with_the_rule():
    rule = Rule(pattern="x", group="  big   party ",
                actions=[{"type": "send", "text": "y"}])
    assert rule.group == "big party"
    assert rule.as_python().startswith("# group: big party\n")
    assert not Rule(pattern="x", actions=[{"type": "send", "text": "y"}]
                    ).as_python().startswith("# group")


def test_the_page_hears_of_a_switch_it_did_not_make():
    session, host, store = make()
    two_modes(store)
    seen = store.version
    typed(session, host, "/group party off")
    assert store.version > seen


def test_a_slash_action_takes_captures_like_any_other():
    session, host, store = make()
    two_modes(store)
    store.upsert({"kind": "alias", "pattern": r"^mode (?P<which>\w+)$", "mode": "regex",
                  "actions": [{"type": "send", "text": "/group {which} on"}]})
    assert host.input("mode solo")
    assert {r.group: r.enabled for r in store.rules if r.group} == {"party": True, "solo": True}
