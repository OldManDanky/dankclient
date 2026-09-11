"""Importing a zMUD settings export: what each line becomes, and that it works.

zMUD exports one command to a line -- #TRIGGER {pattern} {commands} "class"
{options}, #ALIAS, #PATH -- with its own pattern language and speedwalks.
Held to behaviour: an imported trigger fires on the line zMUD's would, an
alias sends what zMUD would have sent, a path walks the same rooms.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import ttimport, zmimport  # noqa: E402
from mud.botstore import RouteStore  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402

HEAD = "#CLASS {areas}\n#CLASS {areas|zombies}\n#CLASS {gagz}\n#CLASS 0\n"


def read(lines: str, rooms=None):
    return ttimport.read([("export.txt", HEAD + lines)], rooms)


def one(line: str, rooms=None):
    found = read(line, rooms)
    assert len(found) == 1, [(f.kind, f.why) for f in found]
    return found[0]


def says(f) -> list[str]:
    return [("wait " if a["type"] == "wait" else "show " if a["type"] == "log" else "")
            + a["text"] for a in f.rule["actions"]]


def brought(lines: str):
    session = Session("127.0.0.1", 1, sec_code=12345)
    sent = []
    session._writer = object()
    session.send = sent.append
    session.queue._send = sent.append
    h = ScriptHost(session, tempfile.mkdtemp())
    h.rules = RuleStore(h, Path(tempfile.mkdtemp()) / "rules.json")
    h.routes = RouteStore(h, Path(tempfile.mkdtemp()) / "routes.json")
    files = [("export.txt", HEAD + lines)]
    found = ttimport.read(files)
    added, problems = ttimport.bring_in(files, range(len(found)), h.rules, h.routes)
    assert not problems, problems
    return h, sent


def test_it_is_told_from_a_tintin_file():
    assert zmimport.is_zmud(HEAD + "#TRIGGER {x} {y}")
    assert not zmimport.is_zmud("#action {x} {y}\n#alias {a} {b}")


def test_a_trigger_its_class_and_whether_it_is_on():
    f = one('#TRIGGER {You feel once again ready for battle.} {kill undead} "areas|zombies"')
    assert (f.kind, f.rule["group"], f.rule["enabled"]) == ("trigger", "areas/zombies", True)
    assert says(f) == ["kill undead"]
    off = one('#TRIGGER {You attack} {palm} "areas" {disable}')
    assert off.rule["enabled"] is False
    named = one('#TRIGGER "amflag" {XPMOB} {kill human} "areas"')
    assert named.rule["pattern"] == "(?i)XPMOB", "the id in front is not the pattern"


def test_zmud_patterns():
    def pat(p):
        return one("#TRIGGER {%s} {x}" % p).rule["pattern"]
    assert pat("^(%w) tells you: (*)$") == r"(?i)^([A-Za-z]+) tells you: (.*)$"
    assert pat("(%d) times for (%d) damage") == r"(?i)(\d+) times for (\d+) damage"
    assert pat("{Maze|Portal|End}") == "(?i)(Maze|Portal|End)"
    assert pat('Archangel screams, ~"Take that~"') == '(?i)Archangel screams, "Take that"'
    assert one("#TRIGGER {x} {y} {case}").rule["pattern"] == "x", "{case} keeps capitals"
    assert "a zMUD function" in one("#TRIGGER {%lower%w pokes} {x}").why or \
        "in a pattern" in one("#TRIGGER {%lower%w pokes} {x}").why


def test_a_trigger_fires_on_the_line_zmuds_would():
    h, sent = brought('#TRIGGER {^(%w) tells you: (*)$} {tell %1 got %2}\n'
                      '#TRIGGER {ready for battle} {kill undead}')
    h._on_line("Friend tells you: hello there", "Friend tells you: hello there")
    h._on_line("You feel once again READY FOR BATTLE.", "You feel once again READY FOR BATTLE.")
    assert sent == ["tell Friend got hello there", "kill undead"], "capitals ignored, as zMUD"


def test_wait_is_milliseconds_and_holds_the_rest():
    assert says(one("#TRIGGER {dealt the killing blow} {#WAIT 3000;dg;kill human}")) \
        == ["wait 3", "dg", "kill human"]


def test_a_wait_at_the_end_is_dropped_so_the_rule_still_comes_in():
    """Two triggers in a real export ended in #WAIT: shown as fine, then
    refused at Import."""
    f = one("#TRIGGER {You attack} {palm;#WAIT 2000}")
    assert says(f) == ["palm"] and any("#WAIT" in n for n in f.notes)
    h, sent = brought("#TRIGGER {You attack} {palm;#WAIT 2000}")
    assert len(h.rules.rules) == 1


def test_a_class_switch_is_a_group_switch_and_takes_what_is_inside():
    f = one("#TRIGGER {zombies are gone} {#T- areas;look}")
    assert says(f) == ["/group areas off", "/group areas/zombies off", "look"]
    assert says(one("#TRIGGER {x} {#T+ zombies}")) == ["/group areas/zombies on"]
    assert "one trigger by its id" in read('#TRIGGER "kid1" {a} {b}\n#TRIGGER {c} {#T+ kid1}')[1].why


def test_gag_and_capture():
    g = one('#TRIGGER {politely asks you for a heal.} {#GAG} "gagz"')
    assert (g.kind, g.rule["gag"], g.rule["group"]) == ("gag", True, "gagz")
    assert "capture window" in one("#TRIGGER {Someone tells you} {#CAP}").why
    both = one("#TRIGGER {spam line} {#GAG;#CAP}")
    assert both.kind == "gag"


def test_an_alias_speedwalks_and_takes_what_you_typed():
    f = one("#ALIAS gocow {search reeds;.3w2sj}")
    assert says(f) == ["search reeds", "w", "w", "w", "s", "s", "ne"]
    h, sent = brought("#ALIAS refo {reforge armour}")
    assert h.input("refo sword") and sent == ["reforge armour sword"], "zMUD appends it too"
    h, sent = brought("#ALIAS gk {kill %1;glance}\n#ALIAS ct {ctell %-1}")
    assert h.input("gk rat") and h.input("ct back soon")
    assert sent == ["kill rat", "glance", "ctell back soon"]


def test_speedwalks():
    assert zmimport.speedwalk(".3n2e") == ["n", "n", "n", "e", "e"]
    assert zmimport.speedwalk(".hjkl") == ["nw", "ne", "sw", "se"], "as the map showed"
    assert zmimport.speedwalk(".2n(climb pipe)e") == ["n", "n", "climb pipe", "e"]
    assert zmimport.speedwalk(".look") is None and zmimport.speedwalk("n") is None


def test_a_path_is_a_route_and_finds_its_start():
    f = one("#PATH knightpath {2en2wh;#T- zombies;#BEEP}")
    assert f.kind == "route" and f.rule["path"] == "e, e, n, w, w, nw"
    assert any("#T-" in n for n in f.notes)
    started = one("#PATH walk {8n8ews}", rooms=lambda moves: [4242])
    assert started.rule["start"] == 4242
    anywhere = one("#PATH walk {8n8ews}", rooms=lambda moves: [1, 2])
    assert anywhere.rule["start"] == 0, "fits many rooms: no start"


def test_a_path_imports_as_a_route_that_walks():
    h, _sent = brought("#PATH chesswalk {4e4n3w}")
    route = h.routes.routes[0]
    assert (route.name, route.steps()) == ("chesswalk", ["e"] * 4 + ["n"] * 4 + ["w"] * 3)


def test_what_does_not_come_across():
    assert "slow walking" in one("#TRIGGER {There is no human here.} {#WAIT 2000;#STEP}").why
    assert "#VARIABLE" in one("#TRIGGER {x} {#VARIABLE hp 1}").why
    assert "Keyboard" in one("#KEY F4 {prot;vest}").why
    assert "rather than every so often" in one("#ALARM {*:*5:00} {slurp}").why
    t = one("#ALARM {*5:00} {moo}")
    assert (t.kind, t.rule["every"]) == ("timer", 300.0)
    assert "not read" in one("#ALIAS golong {{{{home}}}").why, "a broken line, said so"
