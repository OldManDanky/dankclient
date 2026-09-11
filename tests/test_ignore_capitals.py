"""A regex trigger that ignores capitals has to fire whatever the capitals.

Every trigger is first checked for a fixed piece of its pattern -- "ready
for battle" -- before the regex runs, which keeps a thousand triggers cheap.
That check cared about capitals when the pattern did not: `(?i)ready for
battle` never saw "READY FOR BATTLE", and every trigger imported from zMUD,
whose triggers ignore capitals, was one of them.  So is anyone's who took
the guide's advice to start a pattern with (?i).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.triggers import Trigger, TriggerSet  # noqa: E402


def fired(pattern: str, line: str) -> bool:
    ts = TriggerSet()
    ts.add(Trigger(pattern, lambda m: None, "regex"))
    return bool(ts.fire(line))


def test_ignoring_capitals_reaches_past_the_quick_check():
    assert fired(r"(?i)ready for battle", "You feel once again READY FOR BATTLE.")
    assert fired(r"(?i)^(\w+) tells you", "SOMEONE tells you: hi")
    assert fired(r"(?i)Ready For Battle", "ready for battle")


def test_capitals_still_count_where_the_pattern_says_so():
    assert not fired(r"ready for battle", "READY FOR BATTLE")
    assert fired(r"ready for battle", "you are ready for battle")


def test_and_the_quick_check_still_does_its_job():
    ts = TriggerSet()
    t = Trigger(r"(?i)ready for battle", lambda m: None, "regex")
    ts.add(t)
    assert t.literal, "still has a piece to look for first"
    assert not ts.fire("nothing like it")
