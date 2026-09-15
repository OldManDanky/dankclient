"""Kill stats: 3kdb's 3kReport, from the death line, the rounds and xp."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, packs  # noqa: E402
from mud.lines import strip_ansi  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402


def make(tmp):
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    session._writer = object()
    session.shown = []
    session.bus.on(events.TEXT, lambda d: session.shown.append(d.decode("latin-1")))
    host = ScriptHost(session, Path(tmp) / "scripts")
    packs.use_extras(host, ["kills"], Path(tmp))
    return session, host


def line(session, text):
    session.bus.emit(events.LINE, text, text)


def sent(session):
    return session.sent_lines + session.queue.pending


def screen(session):
    return strip_ansi("".join(session.shown))


def status(session):
    return list(session.__dict__.get("pack_status", {}).values())


def kills_of(host):
    return host.aliases.fire(".kills")[0][0].fn.__globals__["kills"]


def rounds(session, *numbers, enemy="Red rat"):
    session.world.player.enemy = enemy
    for n in numbers:
        session.bus.emit(events.ROUND, n)


def xp_answer(session, total, coins=None):
    # As 3K prints it, all five lines.
    line(session, f"You have {total:,} total xp.")
    line(session, "You need 1,144,708,657,152 experience to achieve your next level.")
    line(session, "You have 1,184,584,100,352 to spend.")
    line(session, "XP Gain for the last 30 minutes: 988,784,230")
    line(session, "At this rate you will level in 3 weeks 2 days 20 hours 21 minutes")
    if coins is not None:
        # As 3K prints it: no commas in this one, and two lines more.
        line(session, f"You are carrying {coins} coins in loose change.")
        line(session, "You have 0 coins in bags.")
        line(session, "You have 49052465 coins in the bank.")


def kill(session, mob="Red rat", killer="Player"):
    line(session, f"{mob} gurgles in its own blood as it dies.")
    line(session, f"{killer} dealt the killing blow to {mob}.")


def test_a_kill_is_a_death_line_then_its_killing_blow_and_xp_says_what_it_gave():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        rounds(session, 1)
        assert sent(session) == ["xp", "coins"], "the first fight asks where it starts from"
        xp_answer(session, 10_000, coins=100)
        rounds(session, 1, 2, 3, 4)
        kill(session)
        assert sent(session)[2:] == ["xp", "coins"]
        xp_answer(session, 10_500, coins=112)
        [k] = kills_of(host)
        assert (k["mob"], k["killer"], k["rounds"], k["xp"], k["coins"]) == (
            "Red rat", "Player", 4, 500, 12)
        assert status(session) == [{"label": "Kills", "value": "1", "note": "30K xp/hr",
                                    "rows": [["Last", "Red rat", ["4 rounds", "500 xp"]]]}]


def test_the_answers_it_asked_for_are_hidden_and_yours_are_not():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        rounds(session, 1)
        assert session.gags.fire("You have 10,000 total xp.")
        assert session.gags.fire("You are carrying 100 coins in loose change.")
        assert session.gags.fire("You have 0 coins in bags.")
        assert session.gags.fire("You have 49052465 coins in the bank.")
        xp_answer(session, 10_000, coins=100)
        assert not session.gags.fire("You have 10,000 total xp."), "answered, so shown again"
        assert not session.gags.fire("XP Gain for the last 30 minutes: 988,784,230")
        assert not session.gags.fire("You have 49052465 coins in the bank.")


def test_deaths_that_are_not_kills_are_not_counted():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.input(".kills ask off")
        rounds(session, 1, 2)
        kill(session, mob="Undead")
        kill(session, mob="Celestial Lion")
        kill(session, mob="Angel", killer="red rat")                      # it killed a summon
        assert kills_of(host) == [] and sent(session) == []
        assert json.loads((Path(tmp) / "kills.json").read_text()) == {"ask": False}


def test_rounds_count_from_the_last_kill_and_start_again_with_a_new_fight():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.input(".kills ask off")
        rounds(session, 1, 2, 3)
        kill(session, mob="Red rat")
        rounds(session, 4, 5, 5, 6)
        kill(session, mob="Cur", killer="Buddy")
        rounds(session, 0, 1, 2)
        kill(session, mob="angel")
        assert [k["rounds"] for k in kills_of(host)] == [3, 3, 2]
        assert sent(session) == []


def test_the_report_totals_filters_and_clears():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.input(".kills")
        assert "no kills yet." in screen(session)
        rounds(session, 1)
        xp_answer(session, 1_000, coins=10)
        for mob, gained in (("Red rat", 2_000), ("Cur", 40_000), ("Red rat", 3_000)):
            rounds(session, 1, 2)
            kill(session, mob=mob)
            xp_answer(session, 1_000 + sum(k["xp"] or 0 for k in kills_of(host)) + gained, coins=10)
        host.input(".kills")
        out = screen(session)
        assert "Mob" in out and "Killer" in out and "3 kills  |  2.0 rounds" in out
        assert "xp 45K: 15K a kill" in out
        session.shown.clear()
        host.input("3kReport rat")
        out = screen(session)
        assert "2 kills" in out and "Cur" not in out
        host.input(".kills 1")
        assert "3 kills (the last 1)" in screen(session)
        host.input("3kReport-clear")
        assert kills_of(host) == [] and status(session) == [
            {"label": "Kills", "value": "0", "note": ""}]


def test_short_numbers_read_as_players_write_them():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        short = host.aliases.fire(".kills")[0][0].fn.__globals__["short"]
        assert [short(n) for n in (None, 950, 9_999, 30_000, 1_250_000, 3_000_000_000,
                               5_843_169_611_264)] == [
            "-", "950", "9,999", "30K", "1.2M", "3B", "5.8T"]


def test_damage_dealt_and_taken_are_counted_for_each_kill():
    """3K's numbers, as a player pasted them: raw, before defenses."""
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.input(".kills ask off")
        rounds(session, 1, 2)
        line(session, "You hit Spiral Gun 3 times for 1,200 damage.")
        line(session, "You hit Spiral Gun 1 time for 800 damage.")
        line(session, "Spiral Gun hits you for 2537 damage!")
        kill(session, mob="Spiral Gun")
        line(session, "You hit Cur 1 time for 9161 damage.")
        kill(session, mob="Cur")
        assert [(k["dealt"], k["taken"]) for k in kills_of(host)] == [(2000, 2537), (9161, 0)]
        host.input(".kills")
        out = screen(session)
        assert "Dealt" in out and "Taken" in out
        assert "damage dealt 11.2K, 5,580 a kill  |  taken 2,537, 1,268 a kill" in out


def test_the_killing_blow_is_the_kill_however_the_creature_died():
    """3kdb wanted one of three death lines first; a gun does not gurgle in
    its own blood, and its kill went uncounted."""
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        assert status(session) == [{"label": "Kills", "value": "0", "note": ""}], \
            "loaded, and shown to be"
        host.input(".kills ask off")
        rounds(session, 1, 2, enemy="Spiral Gun")
        line(session, "You hit Spiral Gun 1 time for 9161 damage.")
        line(session, "Spiral Gun explodes in a shower of sparks.")
        line(session, "Player dealt the killing blow to Spiral Gun.")
        [k] = kills_of(host)
        assert (k["mob"], k["killer"], k["rounds"], k["dealt"]) == ("Spiral Gun", "Player", 2, 9161)
        assert status(session) == [{"label": "Kills", "value": "1", "note": "",
                                    "rows": [["Last", "Spiral Gun", ["2 rounds", "9,161 dealt"]]]}]


def test_a_stop_rule_ends_your_own_triggers_but_never_a_packs():
    """A corpse trigger with stop ticked, on the killing blow, hid every kill
    from Kill stats: the pack's trigger comes after the player's rules."""
    from mud.triggers import Trigger

    with tempfile.TemporaryDirectory() as tmp:
        session = Session("127.0.0.1", 1, sec_code=12345)
        session.sent_lines = []
        session.send = session.sent_lines.append
        session.queue._send = session.sent_lines.append
        session._writer = object()
        host = ScriptHost(session, Path(tmp) / "scripts")
        corpse, later = [], []
        host.triggers.add(Trigger(r"dealt the killing blow", lambda m: corpse.append(1),
                                  "regex", "rules", 0, True))
        host.triggers.add(Trigger(r"killing blow", lambda m: later.append(1),
                                  "regex", "rules", 1, False))
        packs.use_extras(host, ["kills"], Path(tmp))
        host.input(".kills ask off")
        line(session, "Someone dealt the killing blow to rat.")
        assert corpse == [1], "the corpse trigger still fires"
        assert later == [], "and still stops the player's own triggers after it"
        assert [k["mob"] for k in kills_of(host)] == ["rat"], "but not the pack's"


def test_only_the_newest_kills_are_kept_but_every_one_is_counted():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.input(".kills ask off")
        g = host.aliases.fire(".kills")[0][0].fn.__globals__
        g["MOST_KEPT"] = 50
        for i in range(120):
            line(session, f"Someone dealt the killing blow to rat {i}.")
        kept = kills_of(host)
        assert len(kept) == 50 and kept[0]["mob"] == "rat 70" and kept[-1]["mob"] == "rat 119"
        assert status(session)[0]["value"] == "120"
