"""Reading the fields 3K wraps its output in.

Lines are taken verbatim from a capture: the room title carries 3K's own
ASCII map after its closing marker, and the description runs over several
lines with the marker alone closing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.markup import Markup  # noqa: E402
from mud.prefixes import Prefixes  # noqa: E402

VORTEX = [
    "-R-_A Vortex (e,w,s,enter)                                      -R-_    1-E-O-^-O",
    "                                                                     |",
    "-D-_The immediate area is extremely blurry and hard to focus on.",
    "Just ahead of you is a raging, swirling vortex.  It extends",
    "as far up into the sky as you can see with no end in sight.",
    "-D-_",
    "-X-_    There are four obvious exits: east, west, south, enter      -X-_",
    "-M-_Zuko, Lazarian's Doberman Pinscher.",
    "-i-A single gold coin.",
]


def read(lines, marks=None):
    marks = marks or Markup()
    for line in lines:
        marks.feed(line)
    return marks


def test_the_title_stops_at_its_closing_marker():
    """3K's own ASCII map follows it on the same line."""
    marks = read(VORTEX)
    assert marks.name == "A Vortex"
    assert marks.exits == ["e", "w", "s", "enter"]


def test_the_description_runs_until_the_marker_alone():
    marks = read(VORTEX)
    assert marks.description.startswith("The immediate area is extremely")
    assert marks.description.endswith("with no end in sight.")
    assert "obvious exits" not in marks.description      # -X-_ is not part of it
    assert "Doberman" not in marks.description           # nor are the contents


def test_a_title_is_only_taken_when_its_exits_agree():
    """A character may have been set up by hand years ago.  A title whose
    brackets disagree with MIP belongs to some other room."""
    marks = read(VORTEX)
    assert marks.take(["n", "s"]) == ("", "")
    assert marks.take(["e", "w", "s", "enter"])[0] == "A Vortex"


def test_titles_queue_because_the_text_runs_ahead_of_mip():
    """A block does not settle until the message after it, so by then the
    next room's title can already have been printed.  Matching on exits picks
    the right one out."""
    marks = Markup()
    for line in ["-R-_A Vortex (e,w,s,enter)  -R-_", "-D-_Blurry.", "-D-_",
                 "-R-_North lane (e,w,n)      -R-_", "-D-_Tiles.", "-D-_"]:
        marks.feed(line)
    assert marks.take(["e", "w", "s", "enter"]) == ("A Vortex", "Blurry.")
    assert marks.take(["e", "w", "n"]) == ("North lane", "Tiles.")
    assert marks.take(["e", "w", "n"]) == ("", "")       # each is taken once


def test_the_markers_come_from_what_the_client_asked_for():
    """They are not guessed: the client is what sets them."""
    marks = Markup.from_prefixes(Prefixes("/nonexistent.json"))
    assert (marks.room, marks.desc) == ("-R-_", "-D-_")


def test_a_character_with_no_markers_set_yields_nothing():
    marks = read(["A Vortex (e,w,s,enter)", "The area is blurry."])
    assert marks.take(["e", "w", "s", "enter"]) == ("", "")
