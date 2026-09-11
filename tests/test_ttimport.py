"""Importing TinTin++: what each thing in a .tin file becomes, and that it works.

Held to behaviour as well as to shape: an imported alias is typed and has to
send what tt++ would have sent; an imported action has to fire on the line
tt++'s would have.  Anything that is real tt++ programming is left out, with
its reason, rather than brought across wrong.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import ttimport  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


def one(text: str, name: str = "actions.tin"):
    found = ttimport.read([(name, text)])
    assert len(found) == 1, [(f.kind, f.why) for f in found]
    return found[0]


def actions(f) -> list[str]:
    return [("wait " if a["type"] == "wait" else "show " if a["type"] == "log" else "")
            + a["text"] for a in f.rule["actions"]]


def host():
    session = Session("127.0.0.1", 1, sec_code=12345)
    sent = []
    session._writer = object()
    session.send = sent.append
    session.queue._send = sent.append
    h = ScriptHost(session, tempfile.mkdtemp())
    h.rules = RuleStore(h, Path(tempfile.mkdtemp()) / "rules.json")
    return h, sent


def brought(text: str):
    """Everything importable in `text`, in a client, and what it sends."""
    h, sent = host()
    found = ttimport.read([("x.tin", text)])
    added, problems = ttimport.bring_in([("x.tin", text)], range(len(found)), h.rules)
    assert not problems, problems
    return h, sent


# --- reading ---------------------------------------------------------------------

def test_an_alias_and_its_arguments():
    f = one("#alias {gk} {kill %1;glance}")
    assert (f.kind, f.rule["mode"], f.rule["pattern"]) == ("alias", "command", "gk")
    assert actions(f) == ["kill {1}", "glance"]
    assert actions(one("#alias {ct} {ctell %0}")) == ["ctell {args}"]


def test_an_alias_that_uses_no_argument_gets_what_was_typed_on_the_end():
    """As tt++ does: `sub rat` with #alias {sub} {cast subjugate}."""
    h, sent = brought("#alias {sub} {cast subjugate}")
    assert h.input("sub rat")
    assert sent == ["cast subjugate rat"]


def test_bodies_over_several_lines_comments_and_shortened_commands():
    text = """/* a block comment */
#NOP -- this is a comment;
#ALI {gs} {
     get all;
     sell all
};
#ACT {You are hungry.} {eat bread} {5}
"""
    found = ttimport.read([("x.tin", text)])
    assert [(f.kind, actions(f)) for f in found] == [
        ("alias", ["get all", "sell all {args}"]), ("trigger", ["eat bread"])]
    assert found[0].source == "x.tin:3", "where it came from, by line"


def test_an_argument_may_start_on_the_next_line():
    """tt++ takes this, and a real actions.tin has it:

        #act {Use your Auras Now!}
        {#foreach ...}

    Split at the line break, both halves were lost without a word."""
    found = ttimport.read([("x.tin", "#act {You are hungry.}\n{eat bread}\n#alias {a} {b}")])
    assert [(f.kind, f.rule["pattern"]) for f in found] == [
        ("trigger", "You are hungry."), ("alias", "a")]
    assert found[1].source == "x.tin:3"


def test_nothing_is_dropped_without_saying_so():
    assert "not read" in one("#action {half an action}").why


def test_patterns():
    def pat(tt):
        return one("#action {%s} {x}" % tt).rule
    assert pat("You are hungry.") == {**pat("You are hungry."), "mode": "contains",
                                     "pattern": "You are hungry."}
    assert pat("^(%w) tells you: %*$")["pattern"] == r"^(\w+) tells you: .*$"
    assert pat("%1 arrives from the %2.")["pattern"] == r"(.*?) arrives from the (.*?)\."
    assert pat("{Cur|rat} dies")["pattern"] == "(Cur|rat) dies"
    assert pat("You have %d gold")["pattern"] == r"You have \d+ gold"
    assert pat("%iyou are hungry")["pattern"] == "(?i)you are hungry"
    assert "ignore capitals" in one("#action {You %ihave} {x}").why


def test_an_action_fires_where_tt_would_have():
    h, sent = brought("#action {^(%w) tells you: hi} {tell %1 hello}\n"
                      "#action {{Cur|rat} arrives} {kill %1}")
    h._on_line("Friend tells you: hi", "Friend tells you: hi")
    h._on_line("A rat arrives.", "A rat arrives.")
    h._on_line("Someone tells you: hi there", "Someone tells you: hi there")
    assert sent == ["tell Friend hello", "kill rat", "tell Someone hello"]


def test_the_exits_trigger_from_the_guide():
    h, sent = brought("#action {There are two obvious exits: light, (%w)} {%1}")
    line = "    There are two obvious exits: light, turnaway                  "
    h._on_line(line, line)
    assert sent == ["turnaway"]


def test_a_class_is_a_group_and_3kdbs_own_class_names_are_not():
    found = ttimport.read([("x.tin", "#class {baura} {open}\n#alias {a} {b}\n"
                                     "#class {baura} {close}\n#alias {c} {d}\n"
                                     "#class {player_aliases} {open}\n#alias {e} {f}")])
    assert [f.rule["group"] for f in found] == ["baura", "tintin", "tintin"]


def test_variables_are_filled_in_unless_something_changes_them():
    f = one("#var {target} {rat}\n#alias {kt} {kill $target}", "vars.tin")
    assert actions(f) == ["kill rat {args}"]
    changing = ("#var {delay} {2}\n#alias {up} {#math delay $delay + 2}\n"
                "#alias {go} {#delay $delay {n}}")
    found = ttimport.read([("x.tin", changing)])
    assert all(f.kind == "skip" for f in found), [(f.kind, f.rule) for f in found]


def test_delay_last_is_a_wait_and_in_the_middle_is_not():
    assert actions(one("#alias {rest} {sleep;#delay 30 {stand}}")) == ["sleep", "wait 30", "stand"]
    assert "#delay with more after it" in one("#alias {rest} {#delay 2 {stand};sleep}").why


def test_3kdbs_idle_check_is_the_deadman():
    f = one("#action {You have no pants.} {#if {!$idle_flag} {stimheal;fdeener}}")
    assert actions(f) == ["stimheal", "fdeener"]
    assert any("deadman" in n for n in f.notes)
    assert one("#ticker {con} {#if !$idle_flag {con 100} {#nop}} {90}").kind == "timer"
    assert "#if" in one("#action {x} {#if {$hp < 10} {flee}}").why


def test_what_is_real_programming_is_left_out_with_the_reason():
    assert one("#action {Use your Auras Now!} {#foreach {$people} {p} {strengthen $p}}").why \
        == "trigger uses #foreach"
    assert "no equivalent" in one("#highlight {red} {Someone}").why
    assert "Keyboard" in one("#macro {\\eOq} {sw}").why
    assert "3kdb hook" in one("#alias {.pre_bot_check} {#nop}").why


def test_repeats_gags_and_tickers():
    assert actions(one("#alias {n5} {#5 n}")) == ["n"] * 5
    g = one("#gag {The rat squeaks}")
    assert (g.kind, g.rule["mode"], g.rule["gag"], g.rule["actions"]) == ("gag", "contains", True, [])
    t = one("#ticker {xp} {xp} {290}")
    assert (t.kind, t.rule["every"], actions(t)) == ("timer", 290.0, ["xp"])
    assert "faster than the game" in one("#ticker {x} {y} {1}").why


def test_your_own_alias_called_from_another_is_put_in_its_place():
    """Commands a rule sends go to 3K, not through aliases -- so a call to
    one of your own is replaced by what it does."""
    h, sent = brought("#alias {gk} {kill %1;glance}\n#alias {k} {gk %0}")
    assert h.input("k rat")
    assert sent == ["kill rat", "glance"]


def test_a_call_into_3kdb_itself_is_named():
    f = one("#alias {mycorpse} {corpsetrig-clear;corpsetrig+ wrap}")
    assert "3kdb's own corpsetrig" in f.why


# --- the page, and importing ---------------------------------------------------------

def test_importing_twice_adds_nothing():
    text = "#alias {gk} {kill %1}\n#gag {The rat squeaks}"
    h, _sent = host()
    found = ttimport.read([("x.tin", text)])
    assert ttimport.bring_in([("x.tin", text)], range(len(found)), h.rules)[0] == 2
    assert ttimport.bring_in([("x.tin", text)], range(len(found)), h.rules)[0] == 0
    shown = ttimport.preview([("x.tin", text)], h.rules.rules)
    assert all(it["have"] for it in shown["items"])
    assert shown["counts"] == {"already there": 2}


def test_only_what_was_ticked_comes_in():
    text = "#alias {a} {b}\n#alias {c} {d}\n#alias {e} {f}"
    h, _sent = host()
    ttimport.bring_in([("x.tin", text)], [0, 2], h.rules)
    assert [r.pattern for r in h.rules.rules] == ["a", "e"]


def test_the_page_reads_and_imports():
    with tempfile.TemporaryDirectory() as tmp:
        session = Session("127.0.0.1", 1, sec_code=12345)
        h = ScriptHost(session, tmp)
        h.rules = RuleStore(h, Path(tmp) / "rules.json")
        web = WebServer(session, scripts=h)
        pushed = []
        web.push = pushed.append
        files = [{"name": "aliases.tin", "text": "#alias {gk} {kill %1}\n#alias {x} {#math a 1}"}]
        web._on_client_message(json.dumps({"t": "ttimport", "op": "read", "files": files}).encode())
        got = pushed[-1]
        assert got["op"] == "read" and got["counts"] == {"alias": 1, "skip": 1}
        web._on_client_message(json.dumps({"t": "ttimport", "op": "import", "files": files,
                                           "ids": [0, 1]}).encode())
        assert pushed[-1] == {"t": "ttimport", "op": "done", "added": 1, "problems": []}
        assert [r.pattern for r in h.rules.rules] == ["gk"]
