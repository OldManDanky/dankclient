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
    assert w.messages[-1]["channel"] == "soul", "a tag of its own, not tell's"


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


# --- a soul you do at a distance ------------------------------------------------
#
# 3K sends it twice, in either order, and prints it once:
#     BAB~you~moo at Buddy.
#     BABx~Buddy~you moo at Buddy.
#     From afar, you moo at Buddy.

def heard(w):
    got = []
    w.on_event(lambda kind, obj: got.append(obj) if kind == "tell" else None)
    return got


def test_your_distant_soul_is_one_message_whichever_half_comes_first():
    for first, second in (("~you~moo at Buddy.", "x~Buddy~you moo at Buddy."),
                          ("x~Buddy~you moo at Buddy.", "~you~moo at Buddy.")):
        w = World()
        told_of = heard(w)
        w.recent.append("From afar, you moo at Buddy.")
        w.apply("BAB", first)
        w.apply("BAB", second)
        w.apply("FFF", "C~100")
        assert [(m["who"], m["text"], m["mine"], m["soul"]) for m in w.messages] == [
            ("Buddy", "you moo at Buddy.", True, True)], (first, list(w.messages))
        assert len(told_of) == 1 and told_of[0].from_me, "no tell *to* you from 'you'"


def test_a_you_with_no_other_half_is_still_shown():
    """Somebody's distant emote could start with "you"; only a partner makes
    it yours.  Shown at the next message, or at the prompt."""
    w = World()
    w.apply("BAB", "~you~are a lovely cow.")
    assert not w.messages
    w.apply("FFF", "C~100")
    assert [(m["who"], m["text"], m["mine"]) for m in w.messages] == [
        ("you", "are a lovely cow.", False)]

    w = World()
    w.apply("BAB", "~you~are a lovely cow.")
    w.flush_echo()                                  # what the prompt does
    assert len(w.messages) == 1


def test_a_different_soul_straight_after_is_not_taken_for_the_other_half():
    w = World()
    w.apply("BAB", "~you~moo at Buddy.")
    w.apply("BAB", "x~Friend~you poke Friend.")
    w.flush_echo()
    assert [m["who"] for m in w.messages] == ["you", "Friend"]


def test_a_tell_you_send_is_untouched():
    w = World()
    w.recent.append("You tell Buddy: you around?")
    w.apply("BAB", "x~Buddy~you around?")
    w.apply("FFF", "C~100")
    assert [(m["text"], m["soul"]) for m in w.messages] == [("you around?", False)]
