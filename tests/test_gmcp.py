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
        assert b'"Room.Info 1"' in out
        assert s.gmcp_on is True


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
