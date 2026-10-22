"""The two MUDs: Three Kingdoms and 3Scapes, and nothing else.

The address used to be a box you typed into, and what you typed never reached
the socket: a character saved on 3scapes.org was still logged in on 3k.org.
So the pair is a choice now, and the choice is what connects.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, worlds  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.profile import Character, Characters, activate  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


def chars(tmp):
    return Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")


def session_at(host, port):
    s = Session(host, port, sec_code=1)
    s.connected = True
    s._writer = type("W", (), {"close": lambda self: None})()
    return s


# --- the pair ---------------------------------------------------------------

def test_there_are_two_and_they_are_the_ones_the_client_plays():
    assert [(w.id, w.host, w.port) for w in worlds.ALL] == [
        ("3k", "3k.org", 3000),
        ("3s", "3scapes.org", 3200),
    ]
    assert worlds.DEFAULT.id == "3k"


def test_an_address_is_read_as_one_of_them_or_as_three_kingdoms():
    assert worlds.of("3scapes.org", 3200).id == "3s"
    assert worlds.of("3k.org", 3000).id == "3k"
    # The host decides, and it is read however it was written down.
    assert worlds.of("3SCAPES.ORG").id == "3s"
    assert worlds.of("3scapes.org:3200").id == "3s"
    # Then the port, which tells the two apart on its own.
    assert worlds.of("", 3200).id == "3s"
    # And anything else is 3K rather than an address nobody can connect to.
    assert worlds.of("nowhere.example", 23).id == "3k"
    assert worlds.of().id == "3k"
    assert worlds.find("nowhere.example", 23) is None


# --- a character carries one ------------------------------------------------

def test_a_character_is_snapped_onto_a_world_whatever_the_file_said():
    """Saved before the choice existed, or typed by hand: either way it has to
    be somewhere the client can actually go."""
    assert Character("Player", host="3scapes.org", port=3200).world.id == "3s"
    assert Character("Other").world.id == "3k"
    junk = Character("Friend", host="nowhere.example", port=23)
    assert (junk.host, junk.port) == ("3k.org", 3000)
    assert junk.public()["world"] == "3k"


def test_the_list_keeps_the_world_through_a_save_and_a_load():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player", host="3scapes.org", port=3200))
        again = chars(tmp)
        assert again.get("Player").world.name == "3Scapes"


# --- and playing them goes there --------------------------------------------

def test_playing_a_3scapes_character_moves_the_session_off_3k():
    """The bug this exists for: the address was saved and then ignored."""
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player", host="3scapes.org", port=3200))
        s = session_at("3k.org", 3000)
        activate(char, c, s, None)
        assert (s.host, s.port) == ("3scapes.org", 3200)
        # A different game, so the old connection goes and a new one is asked
        # for -- rather than the name being typed at 3K's prompt.
        assert s.connected is False
        assert s.wanted is True


def test_playing_a_character_on_the_world_we_are_already_on_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player", host="3k.org", port=3000))
        s = session_at("3k.org", 3000)
        assert s.switch_world(char.host, char.port) is False
        activate(char, c, s, None)
        assert (s.host, s.port, s.connected) == ("3k.org", 3000, True)


def test_a_session_aimed_somewhere_else_is_left_alone():
    """Replays and test servers are neither MUD, and whoever aimed the client
    at one meant it."""
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player", host="3scapes.org", port=3200))
        s = session_at("127.0.0.1", 4000)
        activate(char, c, s, None)
        assert (s.host, s.port, s.connected) == ("127.0.0.1", 4000, True)


# --- the character screen ---------------------------------------------------

def test_the_screen_is_offered_both_and_saves_the_real_address():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        web = WebServer(session_at("3k.org", 3000), characters=c)
        assert [w["name"] for w in web._who()["worlds"]] == [
            "Three Kingdoms", "3Scapes"]
        web._login_op({"op": "save", "character": {
            "name": "Player", "host": "3scapes.org", "port": 3200}})
        assert c.get("Player").world.id == "3s"
        # A page asking for anywhere else gets a world, not an open socket.
        web._login_op({"op": "save", "character": {
            "name": "Other", "host": "evil.example", "port": 25}})
        assert (c.get("Other").host, c.get("Other").port) == ("3k.org", 3000)


def test_the_form_no_longer_takes_a_typed_address():
    page = (Path(__file__).resolve().parents[1]
            / "mud" / "ui" / "index.html").read_text()
    js = (Path(__file__).resolve().parents[1]
          / "mud" / "ui" / "login.js").read_text()
    assert 'id="c-world"' in page
    for gone in ('id="c-host"', 'id="c-port"'):
        assert gone not in page, gone
    assert "c-host" not in js and "c-port" not in js


# --- a map each -------------------------------------------------------------

def test_three_kingdoms_keeps_the_plain_filenames():
    """Its map is the one every installed client already has; renaming it
    would strand all of them."""
    k, s = worlds.ALL
    assert k.file("map.sqlite") == Path("map.sqlite")
    assert k.file("scripts/routes.json") == Path("scripts/routes.json")
    assert s.file("map.sqlite") == Path("map-3scapes.sqlite")
    assert s.file("scripts/routes.json") == Path("scripts/routes-3scapes.json")
    assert s.file(":memory:") == Path(":memory:")


def test_moving_to_3scapes_opens_its_own_map_and_leaves_3ks_alone():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player", host="3scapes.org", port=3200))
        s = session_at("3k.org", 3000)
        s.use_store(Store(Path(tmp) / "map.sqlite"))
        kingdoms = s.store
        room = kingdoms.add_room("Main Street", 0.0)

        moved = []
        s.bus.on(events.WORLD, moved.append)
        activate(char, c, s, None)

        assert Path(s.store.path).name == "map-3scapes.sqlite"
        assert s.store is not kingdoms
        # Empty, because there is no 3kdb for 3Scapes: it grows as you walk.
        assert s.store.room(room) is None
        # And the map, the log and anything reading them moved together.
        assert s.mapper.store is s.store
        assert s.logbook.store is s.store
        assert s.world.log_to is s.logbook
        assert [w.id for w in moved] == ["3s"]

        # Back again, and it is the same file, still holding its room.
        s.switch_world("3k.org", 3000)
        assert s.store is kingdoms
        assert kingdoms.room(room) is not None


def test_3scapes_starts_unlocked_because_there_is_nothing_to_import():
    """3K\'s map is locked to protect 3kdb\'s rooms from invented duplicates.
    3Scapes has no 3kdb, so a locked map would only ever say it was lost."""
    with tempfile.TemporaryDirectory() as tmp:
        s = session_at("3k.org", 3000)
        s.use_store(Store(Path(tmp) / "map.sqlite"))
        assert s.store.locked is True
        s.switch_world("3scapes.org", 3200)
        assert s.store.locked is False
        s.switch_world("3k.org", 3000)
        assert s.store.locked is True


def test_a_client_with_no_map_at_all_still_moves():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player", host="3scapes.org", port=3200))
        s = session_at("3k.org", 3000)          # store=None
        activate(char, c, s, None)
        assert (s.host, s.store, s.mapper) == ("3scapes.org", None, None)


def test_3kdbs_map_is_never_taken_while_playing_the_other_game():
    """It is Three Kingdoms\' geography.  Pulling it onto 3Scapes would write
    one world\'s rooms into the other world\'s file."""
    with tempfile.TemporaryDirectory() as tmp:
        s = session_at("3scapes.org", 3200)
        s.use_store(Store(Path(tmp) / "map-3scapes.sqlite"))
        web = WebServer(s, characters=chars(tmp))
        out = []
        web.push = out.append
        for op in ("check", "pull"):
            asyncio.run(web._update_op({"op": op, "want": ["map"]}))
        assert len(out) == 2
        for said in out:
            assert "3Scapes" in said["error"], said
        # On 3K it is allowed through -- as far as the network, anyway.
        assert WebServer(session_at("3k.org", 3000))._who()["world"]["id"] == "3k"
