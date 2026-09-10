"""A tell, or a soul sent over tell.

BAB carries both the same way -- who, and the words -- and most tells a
player receives are souls: "From afar, Someone moos at you."  Nothing in the
words tells them apart.  What 3K prints does: a tell is printed just before
its BAB as "Someone tells you: ...", every time; a soul is printed as itself,
usually after.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.codes import Tell, told  # noqa: E402
from mud.state import World  # noqa: E402


def bab(world, text):
    world.apply("BAB", text)
    return world.tells[-1]


def test_a_tell_is_printed_just_before_its_bab():
    w = World()
    w.recent.append("Buddy tells you: psst, over here")
    assert bab(w, "~Buddy~psst, over here").soul is False
    w.recent.append("You tell Buddy: on my way")
    assert bab(w, "x~Buddy~on my way").soul is False


def test_a_soul_printed_after_its_bab_is_a_soul():
    w = World()
    w.recent.append("Something unrelated happens.")
    got = bab(w, "~Buddy~moos at you.")
    assert got.soul is True
    assert w.messages[-1]["soul"] is True


def test_a_soul_printed_before_its_bab_is_still_a_soul():
    w = World()
    w.recent.append("From afar, Buddy moos at you.")
    assert bab(w, "~Buddy~moos at you.").soul is True


def test_an_earlier_tell_from_them_does_not_make_a_soul_a_tell():
    w = World()
    w.recent.append("Buddy tells you: hello")
    assert bab(w, "~Buddy~moos at you.").soul is True


def test_words_alone_could_not_have_decided():
    """ "thanks, you rock" reads like a soul, and it was said."""
    said = Tell(from_me=False, who="Buddy", message="thanks, you rock")
    assert told(said, ["Buddy tells you: thanks, you rock"])
    assert not told(said, ["From afar, Buddy thanks, you rock"])
