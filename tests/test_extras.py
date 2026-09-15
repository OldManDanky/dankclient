"""Extras beside a profession -- corpse counts, crafting helpers -- and /block."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, events, packs  # noqa: E402
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
    return session, ScriptHost(session, Path(tmp) / "scripts")


def line(session, text):
    session.bus.emit(events.LINE, text, text)


def sent(session):
    return session.sent_lines + session.queue.pending


def screen(session):
    return strip_ansi("".join(session.shown))


def pack_globals(host, verb):
    return host.aliases.fire(verb)[0][0].fn.__globals__


def status(session):
    return list(session.__dict__.get("pack_status", {}).values())


# --- loading ---------------------------------------------------------------------

def test_every_extra_loads_and_answers_to_every_command_it_names():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        assert packs.use_extras(host, [e.id for e in packs.EXTRAS]) == ["corpses", "crafting"]
        assert not host.errors
        for extra in packs.EXTRAS:
            for command in extra.commands:
                hits = host.aliases.fire(command.split()[0])
                assert hits and hits[0][0].owner == f"pack:{extra.id}", command


def test_only_known_extras_are_kept_once_each_in_the_catalogues_order():
    assert packs.extra_ids(["crafting", "bogus", "Corpse counts", "corpses"]) == [
        "corpses", "crafting"]
    assert packs.extra_ids("corpses") == []
    assert packs.extra_ids(None) == []


def test_extras_load_beside_the_profession_and_an_edit_keeps_their_counts():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        char = chars.put(Character("Player", profession="trapper", extras=["corpses"]))
        activate(char, chars, session, host)
        assert packs.loaded(host).id == "trapper"
        assert packs.loaded_extras(host) == ["corpses"] and packs.matches(host, char)
        line(session, "You picked up 3 corpses into the coffin.")
        edited = Character("Player", profession="trapper", extras=["corpses", "crafting"])
        packs.apply(host, edited, fresh=False)
        assert packs.loaded_extras(host) == ["corpses", "crafting"]
        assert status(session) == ["corpses: 3  (C 3)"], "kept, not reloaded"
        activate(chars.put(Character("Other")), chars, session, host)
        assert packs.loaded(host) is None and packs.loaded_extras(host) == []
        assert status(session) == [], "the Session panel line goes with the pack"


def test_the_character_screen_offers_and_saves_the_extras():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
        web = WebServer(session, scripts=host, characters=chars)
        assert [e["id"] for e in web._who()["extras"]] == ["corpses", "crafting"]
        web._login_op({"op": "save", "character": {"name": "Player",
                                                   "extras": ["crafting", "bogus"]}})
        assert chars.get("Player").extras == ["crafting"]
        assert Characters(Path(tmp) / "profiles").get("Player").extras == ["crafting"]
        web._login_op({"op": "play", "name": "Player"})
        assert packs.loaded_extras(host) == ["crafting"]
        web._login_op({"op": "save", "character": {"name": "Player", "extras": []}})
        assert packs.loaded_extras(host) == []


# --- corpse counts ---------------------------------------------------------------

def test_corpses_follow_3ks_lines_into_the_session_panel():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["corpses"])
        assert status(session) == ["corpses: 0"]
        for text in ("A rat corpse is pulled into the coffin's protective hold!",
                     "A rat corpse is pulled into the coffin's protective hold!",
                     "The coffin expels a corpse!",
                     "You picked up 2 corpses into the coffin.",
                     "The rat corpse hits the frame causing it to get sucked in!",
                     "rat corpse: Taken."):
            line(session, text)
        assert status(session) == ["corpses: 5  (C 3  F 1  I 1)"]
        line(session, "An enchanted coffin (7 corpses).")
        line(session, "You drop the rat corpse.")
        assert status(session) == ["corpses: 8  (C 7  F 1)"]
        line(session, "The coffin expels a corpse!")
        line(session, "There is no reason to 'deslab' here.")
        assert status(session) == ["corpses: 6  (C 6)"]


def test_corpses_count_what_a_look_inside_shows_and_nothing_after():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["corpses"])
        for text in ("The command is: inventory",
                     "A rat corpse {3}",
                     "The corpse of a Cur",
                     "Estimated Capacity: 40%",
                     "A rat corpse"):
            line(session, text)
        count = pack_globals(host, ".corpses")["count"]
        assert count["golem"] == 4
        line(session, "Items you are currently smuggling (2):")
        line(session, ">a rat corpse")
        line(session, ">a shiny rock")
        assert count["smuggle"] == 1


def test_corpse_select_uses_them_in_3kdbs_order():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["corpses"])
        count = pack_globals(host, "corpse_select")["count"]
        for place, expected in (("coffin", ["unwrap"]), ("cooler", ["uncooler corpse"]),
                                ("servant", ["=drop corpse"]),
                                ("inventory", ["unkeep corpse", "drop corpse"]),
                                ("smuggle", ["smuggle remove corpse", "drop corpse"])):
            for p in count:
                count[p] = 0
            count[place] = 2
            count["smuggle"] = 1
            session.sent_lines.clear()
            host.input("corpse_select")
            assert sent(session) == expected, place


def test_no_corpse_left_looks_in_the_inventory_once():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["corpses"])
        line(session, "You have no corpse.")
        line(session, "You have no corpse.")
        assert sent(session) == ["i"]


# --- crafting helpers ------------------------------------------------------------

def test_assembler_assembles_every_five_of_a_kind():
    async def scenario(session, host):
        host.input("assembler")
        await asyncio.sleep(0.05)
        line(session, "Component Name        |   T |  L |  S |  G |  A |  P |")
        line(session, "Essence Of Light      |  19 |  5 |  0 | 10 |  0 |  4 |")
        line(session, "Fragment Of Rage      |   4 |  0 |  0 |  0 |  4 |  0 |")
        line(session, "You have 23/300 items in your satchel.")
        await asyncio.sleep(0.2)

    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        asyncio.run(scenario(session, host))
        one = lambda q: [f"unstash 5 {q} essence of light", "assemble essence of light", "stash all"]
        assert sent(session) == ["stashlist"] + one("legendary") + one("good") * 2
        assert "assembling 3." in screen(session)


def test_autosmelt_goes_round_until_the_ore_runs_out():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        host.input("autosmelt iron ore")
        assert sent(session) == ["unstash2 all worst iron ore"]
        line(session, "You found: [12] [poor] <iron ore>")
        assert sent(session)[1:] == ["12 insert poor iron ore", "smelt", "get all", "stash all"]
        line(session, "You stuff 11 components into your crafting satchel.")
        assert sent(session)[-1] == "unstash2 all worst iron ore"
        line(session, "No objects found.")
        line(session, "You stuff 1 components into your crafting satchel.")
        assert len(sent(session)) == 6 and "no more iron ore" in screen(session)


def test_the_forge_fills_and_fires_each_moulding_until_switched_off():
    async def scenario(session, host):
        pack_globals(host, "forge-on")["wait"] = lambda s: asyncio.sleep(0.01)
        host.input("forge-on")
        line(session, "-INGREDIENTS-")
        line(session, "2 iron shards")
        await asyncio.sleep(0.1)
        line(session, "You have created something new!")
        host.input("forge-off")
        line(session, "3 iron shards")

    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        asyncio.run(scenario(session, host))
        assert sent(session) == ["insert moulding",
                                 "unstash2 worst iron shards", "unstash2 worst iron shards",
                                 "insert iron shards", "insert iron shards",
                                 "fire", "retrieve all", "exa moulding"]


def test_make_gem_takes_the_materials_walks_to_the_kiln_and_makes_it():
    walked = []

    async def go_to(place):
        walked.append(place)
        return True

    async def scenario(session, host, missing):
        g = pack_globals(host, "make-gem")
        g["go_to"] = go_to
        g["wait"] = lambda s: asyncio.sleep(min(s, 0.02))
        host.input("make-gem Minor MIGHT")
        await asyncio.sleep(0.01)
        if missing:
            line(session, "No objects found.")
        await asyncio.sleep(0.2)
        line(session, "You have created something new!")
        await asyncio.sleep(0.05)

    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        asyncio.run(scenario(session, host, missing=False))
        parts = ["aquamarine", "aquamarine dust", "fragment of light"]
        assert sent(session) == ([f"unstash2 legendary {p}" for p in parts]
                                 + ["buy gem of minor might"]
                                 + [f"insert {p}" for p in parts]
                                 + ["insert moulding", "fire", "retrieve gem", "keep gem"])
        assert walked == ["enchanter_shop", "enchanter_kiln"]
        assert "made the gem of Minor Might." in screen(session)

        session.sent_lines.clear()
        walked.clear()
        asyncio.run(scenario(session, host, missing=True))
        assert sent(session) == ["unstash2 legendary aquamarine"] and walked == []
        assert "no legendary aquamarine in your satchel" in screen(session)


def test_gem_and_jewel_lookups_search_names_effects_and_levels():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        host.input("gem-lookup minor might")
        assert "Minor Might  levels 1-5, Str" in screen(session)
        assert "Aquamarine, Aquamarine Dust + Fragment of Light" in screen(session)
        host.input("jewel-lookup 60")
        assert "obsidian shards  levels 60-70" in screen(session)
        host.input("gem-lookup nothing-like-it")
        assert "no gem or effect matching" in screen(session)

        async def typed():
            host.input("make-gem minor")
            await asyncio.sleep(0.02)

        asyncio.run(typed())
        assert "no gem called 'minor'; perhaps Minor Might" in screen(session)
        assert sent(session) == []


def test_tomes_come_six_at_a_time():
    with tempfile.TemporaryDirectory() as tmp:
        session, host = make(tmp)
        packs.use_extras(host, ["crafting"])
        host.input("box-tomes ii")
        assert sent(session)[0] == "get chef volume ii from box" and len(sent(session)) == 6
        host.input("buy-tomes 4")
        assert len(sent(session)) == 6 and "usage: buy-tomes" in screen(session)


# --- /block ----------------------------------------------------------------------

def test_block_asks_every_window_and_says_how_when_wrong():
    session = Session("127.0.0.1", 1, sec_code=1)
    pages, said = [], []
    session.bus.on(events.PAGE, pages.append)
    for text in ("/block Friend", "/unblock friend", "/unblock all", "/blocked",
                 "/block", "/block two words"):
        assert commands.handle(text, session, None, said.append)
    assert pages == [{"t": "block", "op": "add", "name": "Friend"},
                     {"t": "block", "op": "remove", "name": "friend"},
                     {"t": "block", "op": "clear", "name": ""},
                     {"t": "block", "op": "list", "name": ""}]
    assert said == ["usage: /block <name>"] * 2
