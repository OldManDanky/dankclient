"""The guide: Options -> Help and /help <topic>, from one set of Markdown files.

Held to the code as well as rendered.  A guide that names a command the
client does not have, links to a page Options does not have, or shows a
pattern that does not match the line it is shown with, is worse than none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, guide  # noqa: E402
from mud.commands import HELP  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.triggers import Trigger  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def every_body() -> str:
    return "\n".join(t["body"] for t in guide.topics())


def test_the_topics_come_in_order_with_titles_and_summaries():
    topics = guide.topics()
    ids = [t["id"] for t in topics]
    assert ids[:3] == ["start", "triggers", "patterns"]
    assert ids[-1] == "commands", "the command list is generated, and last"
    assert len(ids) == len(set(ids))
    for t in topics:
        assert t["title"] and t["summary"] and t["body"], t["id"]
        assert not t["title"].startswith("#")


def test_every_link_goes_somewhere():
    ids = {t["id"] for t in guide.topics()}
    tabs = set(re.findall(r'data-tab="([^"]+)"', (UI / "index.html").read_text()))
    body = every_body()
    for target in re.findall(r"\]\(#([^)]+)\)", body):
        assert target in ids, f"a link to no topic: #{target}"
    for page in re.findall(r"\]\(options:([^)]+)\)", body):
        assert page in tabs, f"a link to no page of Options: {page}"


def test_every_command_it_names_is_a_command():
    """/wait only exists inside an alias, which the guide says."""
    known = {verb.split()[0] for _t, _b, rows in HELP for verb, _w in rows}
    known |= {"/wait", "/flush", "/groups", "/unalias", "/ungag", "/gags", "/ticks",
              "/untick", "/reload", "/scripts", "/test", "/bots"}
    body = "\n".join(t["body"] for t in guide.topics() if t["id"] != guide.COMMANDS)
    named = set(re.findall(r"(?<![\w/])(/[a-z]+)\b", body))
    missing = sorted(named - known)
    assert not missing, missing
    for verb in sorted(named - {"/wait"}):
        said = []
        assert commands.handle(verb, Session("127.0.0.1", 1, sec_code=1), None,
                               said.append), f"{verb} is not handled"


def test_the_command_topic_is_every_command_there_is():
    body = next(t for t in guide.topics() if t["id"] == guide.COMMANDS)["body"]
    for _t, _b, rows in HELP:
        for verb, _w in rows:
            assert f"`{verb.replace('|', chr(92) + '|')}`" in body, verb


def test_the_worked_examples_match_what_they_are_shown_with():
    """The patterns page shows each of these against a real 3K line."""
    body = next(t for t in guide.topics() if t["id"] == "patterns")["body"]

    def fires(mode, pattern, line):
        assert pattern in body, f"not in the guide any more: {pattern}"
        return Trigger(pattern, lambda m: None, mode).match(line)

    assert fires("regex", r"^(\w+) tells you: (.*)",
                 "Someone tells you: are you there?") == {1: "Someone", 2: "are you there?"}
    assert fires("glob", "* tells you: *", "Someone tells you: hi") == {1: "Someone", 2: "hi"}
    assert fires("regex", r"You have (\d+) gold", "You have 1234 gold coins.") == {1: "1234"}
    exits = "    There are two obvious exits: {}                      "
    assert fires("regex", r"There are two obvious exits: light, (\w+)",
                 exits.format("light, turnaway")) == {1: "turnaway"}
    assert fires("regex", r"^There", exits.format("light, turnaway")) is None, \
        "the guide says ^There does not match the indented line"
    both = r"There are two obvious exits: (?=.*\blight\b)(?:light, )?(?!light\b)(\w+)"
    for order in ("light, turnaway", "turnaway, light"):
        assert fires("regex", both, exits.format(order)) == {1: "turnaway"}, order
    assert fires("regex", both, exits.format("west, east")) is None


def test_what_it_says_about_capitals_is_so():
    assert Trigger("rat", lambda m: None, "contains").match("A Rat arrives.") is None
    assert Trigger("(?i)rat", lambda m: None, "regex").match("A Rat arrives.") == {}
    assert Trigger("GK", lambda m: None, "command").match("gk rat") is not None
    named = Trigger(r"(?P<who>\w+) (\w+)", lambda m: None, "regex").match("Someone waves")
    assert named == {"who": "Someone"}, "with a name, only names are kept -- as it says"


def test_help_prints_a_topic_in_the_output():
    s = Session("127.0.0.1", 1, sec_code=1)

    def helped(word):
        said = []
        commands.handle(f"/help {word}".strip(), s, None, said.append)
        return said[0]

    assert helped("patterns").startswith("PATTERNS AND REGEX")
    assert helped("regex").startswith("PATTERNS AND REGEX"), "a word from a title"
    assert helped("trigger").startswith("TRIGGERS"), "singular or plural"
    assert "is in:" in helped("deadman")
    assert "nothing in the guide" in helped("zzzz")
    assert "The guide -- /help <topic>" in helped("")
    text = helped("patterns")
    assert "**" not in text and "](#" not in text and "`" not in text
    assert r"(\w+)" in text and ".*" in text, "code is shown exactly as written"
    assert "  %w" in text, "the tables are laid out"


def test_the_page_has_the_help_and_the_forms_link_to_it():
    html = (UI / "index.html").read_text()
    for part in ('data-tab="guide"', 'data-pane="guide"', 'id="guide-find"',
                 'id="guide-topics"', 'id="guide-article"', 'src="guide.js"',
                 'data-guide="patterns"', 'data-guide="actions"', 'data-guide="routes"'):
        assert part in html, part
    assert "t: 'guide'" in (UI / "guide.js").read_text()
    assert "window.handleGuide(m)" in (UI / "app.js").read_text()
