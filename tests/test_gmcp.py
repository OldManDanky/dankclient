"""GMCP: the other protocol, and the one thing it tells us that MIP cannot.

3Scapes speaks both.  MIP keeps everything it already parses; GMCP is the
authority on which room this is, because ``Room.Info`` carries the number
and 3K's wire never has.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, gmcp  # noqa: E402
from mud.mapper import Mapper  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.telnet import (DO, DONT, IAC, OPT_GMCP, SB, SB_MOST, SE, WILL,  # noqa: E402
                        TelnetFilter)


def sb(option: int, payload: bytes) -> bytes:
    return bytes([IAC, SB, option]) + payload + bytes([IAC, SE])


# --- the telnet layer -------------------------------------------------------

def test_gmcp_is_the_one_option_we_agree_to():
    f = TelnetFilter()
    _clean, reply, marks, _subs = f.feed(bytes([IAC, WILL, OPT_GMCP]))
    assert reply == bytes([IAC, DO, OPT_GMCP])
    # Said out loud, because agreeing is the moment to subscribe.
    assert marks == [f"opt:on:{OPT_GMCP}"]
    # And everything else is still refused, MCCP above all.
    _clean, reply, marks, _subs = f.feed(bytes([IAC, WILL, 86]))
    assert reply == bytes([IAC, DONT, 86]) and marks == []


def test_a_frame_arrives_whole_and_the_text_around_it_is_untouched():
    f = TelnetFilter()
    clean, _reply, _marks, subs = f.feed(
        b"You see a rat." + sb(OPT_GMCP, b'Room.Info {"num": 42}') + b"> ")
    assert clean == b"You see a rat.> "
    assert subs == [(OPT_GMCP, b'Room.Info {"num": 42}')]


def test_a_frame_split_across_reads_is_still_one_frame():
    f = TelnetFilter()
    whole = sb(OPT_GMCP, b'Room.Info {"num": 7, "name": "Main Street"}')
    subs = []
    for i in range(len(whole)):            # a byte at a time, the worst case
        subs += f.feed(whole[i:i + 1])[3]
    assert gmcp.parse(subs[0][1]) == ("Room.Info",
                                      {"num": 7, "name": "Main Street"})


def test_an_option_we_refused_is_swallowed_and_never_handed_on():
    f = TelnetFilter()
    clean, _reply, marks, subs = f.feed(sb(24, b"\x01TERM") + b"hi")
    assert clean == b"hi" and subs == [] and marks == ["sb:24"]


def test_a_frame_too_big_to_hold_is_dropped_rather_than_truncated():
    """Half a JSON frame is worse than none: it either fails to parse or,
    far worse, parses into something the MUD did not say."""
    f = TelnetFilter()
    f.feed(bytes([IAC, SB, OPT_GMCP]) + b'Room.Map {"rows": "'
           + b"x" * (SB_MOST * 2))
    clean, _reply, _marks, subs = f.feed(bytes([IAC, SE]) + b"after")
    assert subs == [] and clean == b"after"
    # ...and the next one is fine, so one huge frame costs one frame.
    _clean, _reply, _marks, subs = f.feed(sb(OPT_GMCP, b"Core.Ping"))
    assert subs == [(OPT_GMCP, b"Core.Ping")]


# --- frames -----------------------------------------------------------------

def test_what_we_send_is_a_frame_the_mud_can_read():
    assert gmcp.subscribe(["Room.Info 1"]) == sb(
        OPT_GMCP, b'Core.Supports.Set ["Room.Info 1"]')
    assert b'"client": "Dank Mud Client"' in gmcp.hello("9.9.9")
    # Nothing inside a frame may be a bare 0xFF: it would end the
    # subnegotiation early, exactly as it does in ordinary output.
    body = gmcp.frame("Say", "\u00ff \u2014")[3:-2]
    assert bytes([IAC]) not in body


def test_a_frame_we_cannot_read_still_names_itself():
    assert gmcp.parse(b"Core.Ping") == ("Core.Ping", None)
    assert gmcp.parse(b"Room.Info {not json") == ("Room.Info", None)
    assert gmcp.parse(b"") == ("", None)
    assert gmcp.parse(b"Char.Vitals {\"hp\": 90}") == ("Char.Vitals",
                                                       {"hp": 90})


def test_room_info_is_read_however_the_exits_are_written():
    # 3S documents {num, name, area, exits}; the shape of exits is the part
    # that differs between muds, so all three are read.
    assert gmcp.room_info({"num": 42, "exits": {"n": 43, "s": 41}})["exits"] \
        == ["n", "s"]
    assert gmcp.room_info({"num": 42, "exits": ["N", " e "]})["exits"] \
        == ["n", "e"]
    assert gmcp.room_info({"num": 42, "exits": "n~s~u"})["exits"] \
        == ["n", "s", "u"]
    got = gmcp.room_info({"num": "42", "name": "Main Street", "area": "town"})
    assert (got["num"], got["name"], got["area"]) == (42, "Main Street", "town")
    # Without a number it is not a room block -- better the mapper's own
    # reckoning than a room filed under nothing.
    for bad in ({"name": "Main Street"}, {"num": 0}, {"num": "x"}, [], None):
        assert gmcp.room_info(bad) is None


# --- the map ----------------------------------------------------------------

def test_being_told_the_number_needs_no_working_out():
    m = Mapper(Store(":memory:"))
    assert m.here is None
    m.told_room(4200, "Main Street", ["n", "e"])
    assert m.here == 4200
    assert m.store.room(4200)["name"] == "Main Street"
    assert sorted(m.store.exits_of(4200)) == ["e", "n"]
    assert m.candidates == []


def test_the_step_between_two_numbered_rooms_still_makes_the_edge():
    """The MUD names the rooms; which command joined them is ours to know,
    and the edge is what makes the map walkable."""
    m = Mapper(Store(":memory:"))
    m.told_room(4200, "Main Street", ["n"])
    m.sent("n")
    m.told_room(4201, "North Street", ["s"])
    assert m.here == 4201
    assert m.store.destination(4200, "n") == 4201
    # Nothing we sent, nothing to credit: no invented edge.
    m.told_room(9999, "Somewhere Else", [])
    assert m.store.destination(4201, "n") is None


def test_a_room_block_after_it_is_evidence_not_a_second_opinion():
    """Both protocols describe the same arrival.  The text says what is in
    the room; it does not get a vote on which room it is."""
    m = Mapper(Store(":memory:"))
    m.told_room(4200, "Main Street", ["n", "e"])
    here = m.arrived(["n", "e"], ["a fountain"], name="Main Street")
    assert here == 4200 and m.here == 4200
    assert "a fountain" in m.store.exits_of(4200) + ["a fountain"]
    # The block did not arrive as a second visit either.
    assert m.store.room(4200)["visits"] == 1
    # Long enough afterwards it is an arrival like any other, and the mapper
    # works it out as it always has.
    m.told_at -= m.window * 2
    m.sent("n")
    assert m.arrived(["s"], [], name="North Street") != 4200


def test_a_relog_forgets_what_it_was_told():
    m = Mapper(Store(":memory:"))
    m.told_room(4200, "Main Street", ["n"])
    m.unsure()
    assert m.here is None and m.told_at is None


# --- the session ------------------------------------------------------------

class FakeWriter:
    def __init__(self):
        self.sent = bytearray()

    def write(self, data):
        self.sent += data

    def get_extra_info(self, _name):
        return None


def session_with_map(tmp):
    s = Session("3scapes.org", 3200, sec_code=1, jumpstart=False,
                store=Store(Path(tmp) / "map-3scapes.sqlite"))
    s._writer = FakeWriter()
    return s


def test_the_client_subscribes_as_soon_as_the_mud_turns_it_on():
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        s._consume(bytes([IAC, WILL, OPT_GMCP]))
        out = bytes(s._writer.sent)
        assert out.startswith(bytes([IAC, DO, OPT_GMCP]))     # agreed first
        assert b"Core.Hello" in out and b"Core.Supports.Set" in out
        assert b'"Room 1"' in out          # roots, not exact names
        assert s.gmcp_on is True


def test_hello_gives_the_version_number_not_mips_handshake_token():
    """`session.version` is what MIP's `3klient` line wants -- the slug and
    the number run together.  GMCP has a field for the name already, so what
    belongs in `version` is the number on its own."""
    from mud import __version__, SLUG
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        s._consume(bytes([IAC, WILL, OPT_GMCP]))
        out = bytes(s._writer.sent)
        assert f'"version": "{__version__}"'.encode() in out
        assert f'"{SLUG}{__version__}"'.encode() not in out


def test_a_room_frame_moves_the_map_and_is_passed_on():
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        seen = []
        s.bus.on(events.GMCP, lambda package, body: seen.append(package))
        s._consume(sb(OPT_GMCP, b'Core.Supported ["Room.Info 1"]'))
        s._consume(sb(OPT_GMCP,
                      b'Room.Info {"num": 51, "name": "Dock", "exits": {"w": 50}}'))
        assert s.mapper.here == 51
        assert s.store.room(51)["name"] == "Dock"
        assert seen == ["Core.Supported", "Room.Info"]
        assert s.gmcp_offers == ["Room.Info 1"]


def test_a_client_running_without_a_map_still_takes_the_frames():
    s = Session("3scapes.org", 3200, sec_code=1, jumpstart=False)
    s._writer = FakeWriter()
    seen = []
    s.bus.on(events.GMCP, lambda package, body: seen.append(package))
    s._consume(sb(OPT_GMCP, b'Room.Info {"num": 51}'))
    assert s.mapper is None and seen == ["Room.Info"]


def test_three_kingdoms_is_unchanged_because_it_offers_none_of_this():
    with tempfile.TemporaryDirectory() as tmp:
        s = Session("3k.org", 3000, sec_code=1, jumpstart=False,
                    store=Store(Path(tmp) / "map.sqlite"))
        s._writer = FakeWriter()
        s._consume(b"The Market Square\r\n")
        assert s.gmcp_on is False
        assert bytes(s._writer.sent) == b""


def ways(store, room_id) -> dict:
    """{command: destination} for one room, from the edge rows."""
    return {row["command"]: row["to_room"] for row in store.exits_from(room_id)}


# --- the feed as 3Scapes actually sends it ---------------------------------
#
# Room.Info's exits are an object, direction -> the room it leads to, and a
# destination of 0 means "there is a way out and I am not saying where".
# Hidden exits are left out altogether, so an empty object is "nothing to
# tell you" and never "nowhere to go".

def test_exits_are_read_as_a_graph_not_a_list_of_names():
    room = gmcp.room_info({"num": 3872, "name": "On the outer wall",
                           "area": "Angarboda", "exits": {"w": 3873, "e": 0}})
    assert room["exits"] == ["w", "e"]          # still the plain list
    assert room["ways"] == {"w": 3873}          # and where they go
    # 0 is a way out, so it belongs in the list; it is not a destination, so
    # it is not in the graph.
    assert "e" not in room["ways"]


def test_an_exit_list_without_destinations_still_reads():
    """A tilde string or a plain list: the names, and nothing told."""
    assert gmcp.room_info({"num": 7, "exits": "n~se~up"})["exits"] == \
        ["n", "se", "up"]
    assert gmcp.room_info({"num": 7, "exits": ["N", " e "]})["exits"] == \
        ["n", "e"]
    assert gmcp.room_info({"num": 7, "exits": "n~se"})["ways"] == {}


def test_a_room_with_no_exits_is_not_recorded_as_a_dead_end():
    """Hidden exits are not in Room.Info, so {} means the MUD is not saying.

    Writing it down as a fingerprint would teach the map a wall that is not
    there, and the map would then route around a door that opens.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        m = Mapper(store)
        m.told_room(500, "Da Void", [], {})
        assert store.exits_of(500) == []
        assert m.here == 500                    # but we know where we are


def test_the_exits_it_names_are_written_down_as_edges():
    """The map handed over an edge at a time -- including the ways out
    nobody has walked yet.  Unlocked, as 3Scapes' own map is: there is no
    import there to protect."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = False
        m = Mapper(store)
        m.told_room(3872, "On the outer wall", ["w", "e"], {"w": 3873})
        assert ways(store, 3872) == {"w": 3873}
        # The far room exists now, with no name: heard of, not stood in.
        assert store.room(3873)["name"] is None


def test_a_door_onto_its_own_room_is_not_an_edge():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = False
        Mapper(store).told_room(60494, "Layer one of the Sea of Chaos",
                                ["n", "e"], {"e": 60494})
        assert ways(store, 60494) == {}


def into_the_sea(m, steps=2):
    """Walk in, then keep stepping while the room changes under you."""
    m.told_room(266, "A swirling Sea of Chaos", ["enter"])
    m.sent("enter")
    m.told_room(60494, "Layer one of the Sea of Chaos", ["n"])
    for i in range(steps):
        m.sent("n")
        m.told_room(60494, f"Layer {i + 2} of the Sea of Chaos", ["n"])


def test_one_number_for_two_rooms_stops_the_map_learning_from_it():
    """3Scapes generates the Sea of Chaos fresh and gives every layer room
    the same number.  Nothing can tell them apart, so once the client can
    see that, no edge is drawn to or from it -- otherwise the sea gets
    stitched onto wherever you walked in."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = False
        m = Mapper(store)
        into_the_sea(m)
        assert 60494 in m.shared
        m.sent("out")
        m.told_room(900, "Somewhere else entirely", ["s"])
        # The sea is joined to nothing, in either direction -- including the
        # way in, learned in good faith before we knew the number was shared.
        assert ways(store, 60494) == {}
        assert ways(store, 266) == {}


def test_a_room_that_is_simply_renamed_is_left_alone():
    """The signal has to be narrow.  A real room gets renamed -- a quest
    changes it, a builder tidies it -- and that must not cost it its exits.
    What marks the sea is the room changing under you on every step, not a
    name changing once and staying changed."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = False
        m = Mapper(store)
        m.told_room(300, "The old square", ["n"])
        m.sent("n")
        m.told_room(301, "A lane", ["s"])
        m.sent("s")
        m.told_room(300, "The new square", ["n"])      # renamed, and stays
        m.sent("n")
        m.told_room(301, "A lane", ["s"])
        m.sent("s")
        m.told_room(300, "The new square", ["n"])
        assert m.shared == set()
        assert ways(store, 300) == {"n": 301}


def test_one_step_that_lands_on_a_rename_is_not_enough():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = False
        m = Mapper(store)
        into_the_sea(m, steps=1)
        assert 60494 not in m.shared


def test_a_shared_number_is_remembered_between_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.sqlite"
        store = Store(path)
        m = Mapper(store)
        into_the_sea(m)
        store.close()
        again = Store(path)
        assert 60494 in Mapper(again).shared


# --- the receipts -----------------------------------------------------------

def test_the_audit_says_what_was_asked_offered_and_arrived():
    a = gmcp.Audit()
    a.negotiated = True
    a.subscribed(gmcp.VERB, ["Room 1"])
    a.offered = ["Room.Info 1", "Char.Vitals 1"]
    a.took("Room.Info", {"num": 3872, "exits": {"w": 3873}}, 1.0)
    a.took("Room.Info", {"num": 3873, "exits": {"e": 3872}}, 2.0)
    text = "\n".join(a.report())
    assert "Room.Info  x2" in text
    assert "num, exits.w, exits.e" in text          # every field seen, once
    assert "Char" in text                           # offered, not asked for


def test_the_audit_says_when_nothing_has_arrived():
    """The failure that looks like success: negotiated, subscribed, silent."""
    a = gmcp.Audit()
    a.negotiated = True
    a.subscribed(gmcp.VERB, ["Room 1"])
    assert "nothing has arrived yet" in "\n".join(a.report())
    assert a.anything is False


def test_silence_makes_the_client_ask_again_under_the_other_spelling():
    """3S's help calls it Core.Supports; the specification says
    Core.Supports.Set.  We send one, and if nothing comes back we send the
    other and say so."""
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        s._consume(bytes([IAC, WILL, OPT_GMCP]))
        assert gmcp.VERB.encode() in bytes(s._writer.sent)
        s._writer.sent = bytearray()

        s._gmcp_asked_at -= gmcp.QUIET + 1          # a quiet few seconds
        s._consume(b"a prompt, and still no GMCP\r\n")
        out = bytes(s._writer.sent)
        assert gmcp.frame(gmcp.VERB_ALSO, list(gmcp.WANTED)) in out
        assert s._gmcp_asked_again is True

        # Once only, however long the silence lasts.
        s._writer.sent = bytearray()
        s._gmcp_asked_at -= gmcp.QUIET + 1
        s._consume(b"still nothing\r\n")
        assert bytes(s._writer.sent) == b""


def test_one_frame_is_enough_to_settle_the_spelling():
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        s._consume(bytes([IAC, WILL, OPT_GMCP]))
        s._consume(sb(OPT_GMCP, b'Core.Supported ["Room.Info 1"]'))
        s._writer.sent = bytearray()
        s._gmcp_asked_at -= gmcp.QUIET + 1
        s._consume(b"a prompt\r\n")
        assert bytes(s._writer.sent) == b""         # it is working; leave it
        assert s.gmcp.offered == ["Room.Info 1"]


def test_slash_gmcp_prints_the_receipts():
    """Three ways a feed can be silent -- never negotiated, negotiated but
    never subscribed, subscribed but nothing has changed -- look identical
    from the screen and need different fixes.  So the client says which."""
    from mud import commands
    with tempfile.TemporaryDirectory() as tmp:
        s = session_with_map(tmp)
        said: list[str] = []
        assert commands.handle("/gmcp", s, None, said.append) is True
        assert "not negotiated" in said[0]

        s._consume(bytes([IAC, WILL, OPT_GMCP]))
        s._consume(sb(OPT_GMCP, b'Core.Supported ["Room.Info 1"]'))
        s._consume(sb(OPT_GMCP,
                      b'Room.Info {"num": 3872, "name": "On the outer wall",'
                      b' "exits": {"w": 3873}}'))
        said.clear()
        commands.handle("/gmcp", s, None, said.append)
        text = said[0]
        assert "negotiated" in text and "Core.Supports.Set" in text
        assert "Room.Info  x1" in text
        assert "On the outer wall" in text


def test_a_locked_map_does_not_grow_on_what_it_is_told_either():
    """`/lock` means the map stops growing.  Rooms named in another room's
    exits are rooms nobody has stood in, so adding them is growth, and a
    locked map must refuse them exactly as it refuses a room walked into.
    Where we are standing is still filed: that is identity, not growth."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "m.sqlite")
        store.locked = True
        m = Mapper(store)
        m.told_room(3872, "On the outer wall", ["w"], {"w": 3873})
        assert m.here == 3872 and store.room(3872) is not None
        assert ways(store, 3872) == {}
        assert store.room(3873) is None

        store.locked = False
        m.told_room(3872, "On the outer wall", ["w"], {"w": 3873})
        assert ways(store, 3872) == {"w": 3873}


# --- Core.Supported, as 3Scapes answers it ---------------------------------

def test_core_supported_is_an_object_not_a_list():
    """The specification says a list of names; 3Scapes sends package -> 1
    if we are subscribed, 0 if it is only on offer.  Read as a list it
    stringified the whole dict and reported a package called "{'Balatro"."""
    a = gmcp.Audit()
    a.negotiated = True
    a.subscribed(gmcp.VERB, ["Char 1"])
    a.offered = {"Char.Vitals": 1, "Room.Info": 1, "Balatro.Cards": 0}
    text = "\n".join(a.report())
    assert "subscribed (2): Char.Vitals, Room.Info" in text
    assert "offered, not asked for (1): Balatro.Cards" in text
    assert "{'" not in text


def test_the_list_shape_still_reads():
    a = gmcp.Audit()
    a.negotiated = True
    a.subscribed(gmcp.VERB, ["Char 1"])
    a.offered = ["Char.Vitals 1", "Balatro.Cards 1"]
    text = "\n".join(a.report())
    assert "subscribed (1): Char.Vitals" in text
    assert "offered, not asked for (1): Balatro.Cards" in text


def test_a_package_that_arrives_without_being_offered_is_named():
    """Core.Supported is not exhaustive.  3Scapes sends Guild.Config,
    Guild.Stats and more that it never names there, so what turned up
    anyway is worth saying -- it is how the next package gets found."""
    a = gmcp.Audit()
    a.negotiated = True
    a.subscribed(gmcp.VERB, ["Guild 1"])
    a.offered = {"Guild.State": 1}
    a.took("Guild.State", {"pu": 9393}, 1.0)
    a.took("Guild.Config", {"guild": "gentech"}, 2.0)
    line = [l for l in a.report() if "without being offered" in l]
    assert line == ["  arrived without being offered: Guild.Config"]
