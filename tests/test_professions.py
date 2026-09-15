"""Profession packs: 3kdb's modules/professions as scripts, one per character."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, packs as professions  # noqa: E402
from mud.lines import strip_ansi  # noqa: E402
from mud.profile import Character, Characters, activate  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


def make(tmp):
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    session._writer = object()
    session.shown = []
    session.bus.on(events.TEXT, lambda d: session.shown.append(d.decode("latin-1")))
    host = ScriptHost(session, Path(tmp) / "scripts")
    return session, host


def line(session, text):
    session.bus.emit(events.LINE, text, text)


def sent(session):
    return session.sent_lines + session.queue.pending


def screen(session):
    return strip_ansi("".join(session.shown))


def pack_global(host, verb, name):
    """A pack's own module-level value, reached through one of its aliases."""
    hit = host.aliases.fire(verb)[0][0]
    return hit.fn.__globals__[name]


# --- the catalogue and loading ----------------------------------------------

def test_every_profession_loads_and_answers_to_every_command_it_names():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        for prof in professions.PROFESSIONS:
            assert professions.use(host, prof.id, Path(tmp)) is prof, host.errors
            assert not host.errors
            for command in prof.commands:
                hits = host.aliases.fire(command.split()[0])
                assert hits and hits[0][0].owner == f"pack:{prof.id}", command
            assert f"[{prof.name}] loaded" in screen(session)


def test_find_takes_an_id_or_the_name_profs_prints_and_nothing_else():
    assert professions.find("golem_master").name == "Golem Master"
    assert professions.find("Golem Master").id == "golem_master"
    assert professions.find("") is None
    assert professions.find("bard") is None
    ids = [p["id"] for p in professions.listing()]
    assert ids == sorted(ids) and len(ids) == 6


def test_one_loads_at_a_time_and_none_unloads_it():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "trapper")
        professions.use(host, "reforger")
        assert [n for n in host.registries if n.startswith("pack:")] == [
            "pack:reforger"]
        assert not host.aliases.fire(".traps")
        assert professions.use(host, "") is None
        assert professions.loaded(host) is None
        assert not host.aliases.fire("refk")


def test_rescanning_the_scripts_folder_keeps_the_pack():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        host.dir.mkdir()
        (host.dir / "trapper.py").write_text("@alias('mine', mode='command')\n"
                                             "def mine(m):\n    log('mine')\n")
        host.load_all()
        professions.use(host, "trapper")
        host.reload_changed()
        assert professions.loaded(host).id == "trapper"
        # A player's own trapper.py is a different thing with the same stem.
        assert host.aliases.fire("mine") and host.aliases.fire(".traps")


def test_profs_sets_the_level_and_names_a_different_profession_once():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "herbologist")
        level = pack_global(host, ".herbs", "level")
        line(session, "Profession #1 : Herbologist (Level 12) [some text]")
        assert level() == 12
        line(session, "Profession #1 : Trapper (Level 3)")
        line(session, "Profession #1 : Trapper (Level 3)")
        assert screen(session).count("3K says your first profession is Trapper") == 1
        assert level() == 12


# --- the characters -----------------------------------------------------------

def test_a_character_keeps_its_profession_and_the_browser_sees_it():
    with tempfile.TemporaryDirectory() as tmp:
        chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        chars.put(Character("Player", profession="trapper"))
        again = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        assert again.get("Player").profession == "trapper"
        assert again.public()[0]["profession"] == "trapper"


def test_playing_a_character_loads_theirs_and_not_the_last_ones():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        activate(chars.put(Character("Player", profession="reforger")), chars,
                 session, host)
        assert professions.loaded(host).id == "reforger"
        activate(chars.put(Character("Other")), chars, session, host)
        assert professions.loaded(host) is None


def test_the_character_screen_saves_it_and_a_change_while_playing_loads_now():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        web = WebServer(session, scripts=host, characters=chars)
        assert [p["id"] for p in web._who()["professions"]][0] == "golem_master"
        web._login_op({"op": "save", "character": {"name": "Player",
                                                   "profession": "marshal"}})
        assert chars.get("Player").profession == "marshal"
        web._login_op({"op": "play", "name": "Player"})
        assert professions.loaded(host).id == "marshal"
        web._login_op({"op": "save", "character": {"name": "Player",
                                                   "profession": "Trapper"}})
        assert professions.loaded(host).id == "trapper"
        web._login_op({"op": "save", "character": {"name": "Player",
                                                   "profession": "bard"}})
        assert chars.get("Player").profession == ""
        assert professions.loaded(host) is None


# --- what each one does ------------------------------------------------------

def test_reforger_reforges_from_the_largest_amount_down():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "reforger")
        host.input("ref plate armour fire")
        assert sent(session) == [f"reforge plate armour with {a} from fire to defense"
                                 for a in ("loads", "lots", "some", "little")]
        session.sent_lines.clear()
        host.input("refg shroud fire")
        assert sent(session)[0] == "reforge shroud on ground with loads from fire to defense"
        session.sent_lines.clear()
        host.input("ref shroud")
        assert sent(session) == [] and "usage: ref" in screen(session)
        host.input("refk1")
        assert sent(session) == ["drop forge", "unkeep knife", "buy knife",
                                 "reforge knife with little from edged to critical",
                                 "dispose knife", "get forge", "keep forge"]


def test_golem_master_takes_a_part_a_corpse_and_rebuilds_what_expires():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "golem_master")
        host.input("build_golem companion")
        assert sent(session) == []
        line(session, "Buddy dealt the killing blow to rat.")
        assert sent(session) == ["golemize corpse head", "wrap", "get all"]
        line(session, "Buddy dealt the killing blow to rat.")
        assert len(sent(session)) == 3, "a kill with nothing waiting does nothing"
        for part, following in (("head", "torso"), ("torso", "limbs")):
            session.sent_lines.clear()
            line(session, f"You quickly set to work and deftly remove the {part} from corpse.")
            line(session, "Buddy dealt the killing blow to rat.")
            assert sent(session)[0] == f"golemize corpse {following}"
        session.sent_lines.clear()
        line(session, "You quickly set to work and deftly remove the limbs from corpse.")
        assert sent(session) == ["golem build companion"]
        line(session, "Buddy dealt the killing blow to rat.")
        assert sent(session)[1:] == ["wrap all", "get all", "put all in disc"]
        session.sent_lines.clear()
        line(session, "Your golem Cur has expired.")
        line(session, "Buddy dealt the killing blow to rat.")
        assert sent(session)[0] == "golemize corpse head"


def test_golem_master_fills_until_the_golem_is_full():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "golem_master")
        host.input("fill_golem")
        line(session, "You unkeep a preservation.")
        assert sent(session) == ["unkeep preservation", "give preservation to golem"] * 2
        line(session, "Golem can't carry that much more.")
        line(session, "You unkeep a preservation.")
        assert sent(session)[4:] == ["golem inventory", "i"]


def test_herbologist_says_how_long_a_herb_lasted_and_what_it_does():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "herbologist")
        line(session, "You eat the pinnacle nettle.")
        line(session, "The effects of the pinnacle nettle wear off.")
        assert "pinnacle nettle (+dodge) lasted 0 seconds." in screen(session)
        host.input(".herbs")
        assert "lasted 0s last time" in screen(session)
        assert sent(session) == []


def test_marshal_rallies_once_a_fight_and_only_when_asked():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "marshal", Path(tmp))
        line(session, "A surge of leadership rushes through your veins, and more.")
        session.world.player.enemy = "Red Rat"
        session.bus.emit(events.ROUND, 8)
        assert sent(session) == [], "all four start off"
        host.input(".rallycry offensive on")
        host.input(".rallycry heal on")
        assert json.loads((Path(tmp) / "marshal.json").read_text()) == {
            "offensive": True, "heal": True}
        for n in (6, 8, 9):
            session.bus.emit(events.ROUND, n)
        assert sent(session) == ["rallycry offensive rat", "rallycry heal"]
        session.bus.emit(events.ROUND, 0)
        line(session, "You have already exhausted the magic of the marshal's standard!")
        session.bus.emit(events.ROUND, 8)
        assert len(sent(session)) == 2, "no charges, no rallycry"


def test_trapper_draws_the_rucksack_as_one_table_and_hides_the_lines():
    lines = ["You peer inside your rucksack to see what you have stored within.",
             "You have 5/10 traps stored in your rucksack.",
             "The traps stored are: blind, blind, slow, stun and blind.",
             "Wood :  3   Metal :  4   Hide :  4 (11/33 items)",
             "You can launch 2 traps right now."]
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "trapper", Path(tmp))
        for text in lines:
            assert session.gags.fire(text), text
            line(session, text)
        table = screen(session).split("loaded:")[1]
        assert "blind: 3  slow: 1  stun: 1" in table and "(11/33 items)" in table
        widths = {len(row) for row in table.split("\r\n") if row.startswith(("+", "|"))}
        assert len(widths) == 1, "every row of the box is the same width"


def test_trapper_scrounges_in_the_order_kept_with_the_character():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "trapper", Path(tmp))
        host.input(".scrounge+ hide")
        host.input(".scrounge+ hide")
        professions.use(host, "trapper", Path(tmp))      # the next login
        host.input(".scrounge rat")
        line(session, "You cannot find any suitable hide on rat.")
        line(session, "You find a nice chunk of metal on rat for your rucksack.")
        line(session, "You cannot find any suitable metal on rat.")
        assert sent(session) == ["scrounge hide from rat", "scrounge metal from rat"]


def test_transmuter_reads_the_satchel_then_burns_what_the_level_can_work():
    async def scenario(session, host):
        pack_global(host, "transmute_burn", "burn")          # loaded
        host.aliases.fire("transmute_burn")[0][0].fn.__globals__["SETTLE"] = 0.2
        host.input("transmute_burn train")
        await asyncio.sleep(0.1)
        line(session, "Profession #1 : Transmuter (Level 11)")
        await asyncio.sleep(0.15)
        for row in ("Component Name   |   T |  L |  S |  G |  A |  P |",
                    "Aquamarine       |   6 |  0 |  0 |  0 |  0 |  6 |",
                    "Fragment of Light |  7 |  0 |  0 |  0 |  3 |  4 |",
                    "Mithril Ore      |   9 |  0 |  0 |  0 |  0 |  9 |"):
            line(session, row)
        line(session, "You have 22/300 items in your satchel.")
        await asyncio.sleep(0.1)
        line(session, "Pfffzzzt!  You transmute: 2 fragment of light")
        await asyncio.sleep(0.4)

    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "transmuter")
        asyncio.run(scenario(session, host))
        # train at 11: aquamarine stopped giving experience at 10, mithril
        # ore cannot be worked until 33; below 100, three averages make a good.
        assert sent(session) == [
            "profs", "stashlist",
            "unstash poor fragment of light", "unstash poor fragment of light",
            "transmute 2 fragment of light quality to average",
            "unstash poor fragment of light", "unstash poor fragment of light",
            "transmute 2 fragment of light quality to average",
            "unstash average fragment of light", "unstash average fragment of light",
            "unstash average fragment of light",
            "transmute 3 fragment of light quality to good",
            "stash all"]
        assert "you transmuted 1 materials." in screen(session)


def test_transmuter_upgrades_one_lot_by_the_level_100_ratio():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "transmuter")
        line(session, "Profession #1 : Transmuter (Level 100)")
        asyncio.run(_input(host, "transmute_ug heart of soul good"))
        assert sent(session) == ["unstash good heart of soul"] * 3 + [
            "transmute 3 heart of soul quality to superior", "stash all"]


def test_transmuter_counts_colour_resets():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        professions.use(host, "transmuter")
        for n in (3, 3, 5):
            line(session, f"Your transmuter's stone bursts with {n} new colours!")
        host.input("transmuter-stats")
        assert "3 resets, 3.67 stones each on average" in screen(session)
        assert "3 stones: 2 times (67%)" in screen(session)


async def _input(host, text):
    host.input(text)
    await asyncio.sleep(0.05)
