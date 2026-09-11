"""Importing a CMUD XML export: what each element becomes, and that it works.

CMUD is zMUD's successor and speaks zMUD's language inside, but exports XML:
nested <class> elements, and settings zMUD left to guesswork said outright --
regex="true", case="true", autoappend="true", enabled="false".
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import cmimport, ttimport  # noqa: E402
from mud.botstore import RouteStore  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402

XML = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<cmud>
<window name="3k" width="851" height="517">
  <alias name="gk" autoappend="true"><value>kill %1;glance</value></alias>
  <alias name="sub" autoappend="true"><value>cast subjugate</value></alias>
  <alias name="plain"><value>cast subjugate</value></alias>
  <alias name="lines"><value>#T+ zombies
kill undead
look</value></alias>
  <var name="'crown">amulet</var>
  <alias name="wearit"><value>wear @crown</value></alias>
  <class name="areas">
    <class name="zombies" enabled="false">
      <trigger priority="10"><pattern>ready for battle</pattern><value>#WA 500
kill undead</value></trigger>
    </class>
  </class>
  <trigger priority="20" regex="true"><pattern>(\\w+) tells you: (.*)</pattern><value>tell %1 got %2</value></trigger>
  <trigger priority="21" regex="true" case="true"><pattern>Exact Case</pattern><value>x</value></trigger>
  <trigger priority="30"><pattern>Caesar keys in</pattern><value>#GAG</value>
    <trigger type="Loop Lines" param="2"><pattern>loss of power</pattern><value>#GAG</value></trigger>
  </trigger>
  <trigger priority="40" type="Wait" param="2000"><pattern>y</pattern><value>z</value></trigger>
  <trigger priority="45" type="Alarm"><pattern>*5:00</pattern><value>moo</value></trigger>
  <trigger priority="50"><pattern>zombies are gone</pattern><value>#4N;.2s(climb pipe)j</value></trigger>
  <macro key="F1"><value>look</value></macro>
  <button priority="1"><caption>go</caption><value>n</value></button>
</window>
<window name="Tells" host="none">
  <trigger priority="1"><pattern>tells you</pattern><value>#beep</value></trigger>
</window>
</cmud>"""


def found():
    return ttimport.read([("RicCmud.xml", XML)])


def by(first: str):
    hits = [f for f in found() if first in f.text]
    assert len(hits) == 1, [(f.text, f.why) for f in found()]
    return hits[0]


def says(f) -> list[str]:
    return [("wait " if a["type"] == "wait" else "") + a["text"] for a in f.rule["actions"]]


def brought():
    session = Session("127.0.0.1", 1, sec_code=12345)
    sent = []
    session._writer = object()
    session.send = sent.append
    session.queue._send = sent.append
    h = ScriptHost(session, tempfile.mkdtemp())
    h.rules = RuleStore(h, Path(tempfile.mkdtemp()) / "rules.json")
    h.routes = RouteStore(h, Path(tempfile.mkdtemp()) / "routes.json")
    files = [("RicCmud.xml", XML)]
    added, problems = ttimport.bring_in(files, range(len(ttimport.read(files))),
                                        h.rules, h.routes)
    assert not problems, problems
    return h, sent


def test_it_is_told_from_the_others():
    assert cmimport.is_cmud(XML)
    assert not cmimport.is_cmud("#TRIGGER {x} {y}\n#CLASS 0")


def test_autoappend_is_cmuds_to_say():
    h, sent = brought()
    assert h.input("sub rat") and h.input("plain rat")
    assert sent == ["cast subjugate rat", "cast subjugate"]


def test_cmud_appends_to_every_command_until_an_argument_is_used():
    """Not zMUD's way: "zMUD only appended to the last command", and CMUD
    appends to each until a parameter has been referenced."""
    xml = XML.replace('<alias name="plain">',
                      '<alias name="both" autoappend="true"><value>wield;wear</value></alias>\n'
                      '  <alias name="mixed" autoappend="true"><value>prep;kill %1;loot</value></alias>\n'
                      '  <alias name="plain">')
    got = {f.rule["pattern"]: [a["text"] for a in f.rule["actions"]]
           for f in ttimport.read([("RicCmud.xml", xml)]) if f.kind == "alias"}
    assert got["both"] == ["wield {args}", "wear {args}"]
    assert got["mixed"] == ["prep {args}", "kill {1}", "loot"]


def test_a_line_break_is_a_command_break():
    assert says(by("<alias lines>")) == ["/group areas/zombies on", "kill undead", "look"]
    assert says(by("ready for battle")) == ["wait 0.5", "kill undead"]


def test_a_class_switched_off_switches_off_what_is_in_it():
    f = by("ready for battle")
    assert (f.rule["group"], f.rule["enabled"]) == ("areas/zombies", False)


def test_regex_and_case_as_cmud_says():
    assert by("tells you: (.*)").rule["pattern"] == r"(?i)(\w+) tells you: (.*)"
    assert by("Exact Case").rule["pattern"] == "Exact Case"
    h, sent = brought()
    h._on_line("FRIEND tells you: hi", "FRIEND tells you: hi")
    assert sent == ["tell FRIEND got hi"]


def test_a_regex_that_asks_for_capitals_keeps_them():
    """CMUD's regex ignores capitals unless the pattern starts (?-i) -- the
    way its forum gives, since its help does not say."""
    xml = XML.replace("<pattern>Exact Case</pattern>", "<pattern>(?-i)Exact Case</pattern>")
    xml = xml.replace('regex="true" case="true"', 'regex="true"')
    f = [f for f in ttimport.read([("RicCmud.xml", xml)]) if "Exact Case" in f.text][0]
    assert f.kind == "trigger" and f.rule["pattern"] == "Exact Case", (f.kind, f.why)


def test_variables_are_filled_in():
    assert says(by("<alias wearit>")) == ["wear amulet {args}"] or \
        says(by("<alias wearit>")) == ["wear amulet"]


def test_repeats_and_speedwalks():
    assert says(by("zombies are gone")) == ["N"] * 4 + ["s", "s", "climb pipe", "ne"]


def test_alarms_are_timers():
    t = by("*5:00")
    assert (t.kind, t.rule["every"]) == ("timer", 300.0)


def test_what_does_not_come_across():
    assert "further states" in by("Caesar keys in").why
    assert "'Wait' trigger" in by("<trigger> y").why
    assert "Keyboard" in by("<macro").why
    assert "no buttons" in by("<button").why
    assert "'Tells' window" in [f for f in found() if f.text == "<trigger> tells you"][0].why


def test_it_all_imports():
    h, _sent = brought()
    assert {r.pattern for r in h.rules.rules if r.kind == "alias"} == {"gk", "sub", "plain", "lines", "wearit"}
