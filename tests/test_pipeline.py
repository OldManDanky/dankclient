"""socket bytes -> telnet -> scanner -> world, the whole path."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.scanner import Message, Scanner, Text  # noqa: E402
from mud.state import World  # noqa: E402
from mud.telnet import DO, IAC, WILL, WONT, DONT, TelnetFilter  # noqa: E402

GLINE1 = "<cMthd>: <yTiger>    <cC>: <rOFF>"
GLINE2 = "G2N: <y81094877>    <cChi Focus>: <gNormal>    <yAE>: <g14>/83%"


def mip(sec: str, body: str) -> bytes:
    return f"#K%{sec}{len(body):03d}{body}".encode("latin-1")


def drive(chunks, sec="12345"):
    tel, scan, world = TelnetFilter(), Scanner(), World()
    replies, text = bytearray(), bytearray()
    for chunk in chunks:
        clean, reply, _ = tel.feed(chunk)
        replies += reply
        for ev in scan.feed(clean):
            if isinstance(ev, Text):
                text += ev.data
            elif ev.sec == sec:
                world.apply(ev.code, ev.data)
    return world, bytes(text), bytes(replies)


def test_telnet_negotiation_is_stripped_and_refused():
    stream = (
        bytes((IAC, WILL, 86))          # MCCP2 -- must be refused
        + b"Welcome to 3Kingdoms!\n"
        + bytes((IAC, DO, 24))          # TTYPE
    )
    world, text, replies = drive([stream])
    assert text == b"Welcome to 3Kingdoms!\n"
    assert replies == bytes((IAC, DONT, 86)) + bytes((IAC, WONT, 24))


def test_iac_inside_a_mip_payload_does_not_corrupt_the_count():
    """An unfiltered 0xFF would shift every byte after it."""
    body = "BABx~Buddy~moo"
    header = b"#K%12345" + f"{len(body):03d}".encode()
    # split the payload and shove a telnet option through the middle of it
    stream = header + body[:6].encode() + bytes((IAC, WILL, 86)) + body[6:].encode()
    world, text, _ = drive([stream])
    assert text == b""                  # nothing leaked


def test_full_room_and_status_update():
    chunks = [
        mip("12345", "DDD"),                                    # room change
        mip("12345", "HAAnpc~Marble Monolith~A huge marble monolith~"
                     "exa #N/say hi, #N/consider #N/kill #N"),
        mip("12345", "HAAnpc~a goblin~A small goblin~kill #N"),
        mip("12345", "BADControl Center"),
        mip("12345", f"FFFA~312~B~472~C~300~D~425~I~{GLINE1}~J~{GLINE2}"),
        b"You are standing in the Control Center.\n",
    ]
    world, text, _ = drive(chunks)

    p = world.player
    assert (p.hp, p.max_hp, p.sp, p.max_sp) == (312, 472, 300, 425)
    assert p.hp_pct == 66.1

    assert world.room.short == "Control Center"
    assert len(world.room.mobs()) == 2
    assert world.room.find("goblin").command("kill") == "kill a goblin"

    g = p.gline
    assert g["Mthd"].value == "Tiger"
    assert g["C"].status == "bad"
    assert g["Chi Focus"].value == "Normal"
    assert g["AE"].value == "14/83%"

    assert text == b"You are standing in the Control Center.\n"


def test_room_change_clears_stale_contents():
    world, _, _ = drive([
        mip("12345", "DDD"),
        mip("12345", "HAAnpc~a goblin~A small goblin~kill #N"),
        mip("12345", "DDDn e u"),          # moved
    ])
    assert world.room.contents == []
    assert world.room.exits == ["n", "e", "u"]


def test_foreign_security_code_is_ignored():
    world, _, _ = drive([mip("99999", "FFFA~999")])
    assert world.player.hp is None


def test_change_listener_reports_transitions():
    tel, scan, world = TelnetFilter(), Scanner(), World()
    seen = []
    world.on_change(lambda n, new, old: seen.append((n, old, new)))
    for ev in scan.feed(mip("12345", "FFFA~312") + mip("12345", "FFFA~180")):
        if isinstance(ev, Message):
            world.apply(ev.code, ev.data)
    assert seen == [("hp", None, 312), ("hp", 312, 180)]


def test_periodic_refresh_does_not_empty_the_room():
    """Observed on the wire: room entry is DDD + H** records, but a couple of
    seconds later BAD + a redundant DDD arrives carrying nothing.  Clearing on
    both would wipe the room contents right after you walked in."""
    world, _, _ = drive([
        mip("12345", "DDDw~d~u"),                                   # entry
        mip("12345", "HAAnpc~Cur~Cur, the tradesman's dog~kill #N"),
        mip("12345", "HABnoun~street~street~exa #N/search #N"),
        mip("12345", "BADThe Trading Post (w,d,u)"),                # refresh
        mip("12345", "DDDw~d~u"),                                   # ...echo
    ])
    assert [o.name for o in world.room.contents] == ["Cur"]
    assert [o.name for o in world.room.scenery] == ["street"]
    assert world.room.exits == ["w", "d", "u"]


def test_genuine_room_change_still_clears():
    world, _, _ = drive([
        mip("12345", "DDDw~d~u"),
        mip("12345", "HAAnpc~Cur~Cur, the tradesman's dog~kill #N"),
        mip("12345", "DDDe~w~s~n"),          # standalone -> real move
        mip("12345", "HABnoun~plaque~plaque~exa #N"),
    ])
    assert world.room.contents == []
    assert [o.name for o in world.room.scenery] == ["plaque"]


def test_tells_and_chat_are_captured():
    events = []
    world, _, _ = drive([mip("12345", "DDD")])   # warm-up
    world.on_event(lambda kind, obj: events.append((kind, obj)))
    world.apply("BAB", "~Friend~do you need an xmute?")
    world.apply("CAA", "ctell~Clan Sa~Friend~[Clan] Friend : moo")
    assert world.tells[-1].who == "Friend" and world.tells[-1].from_me is False
    assert world.chat[-1].channel == "Clan Sa"
    assert [k for k, _ in events] == ["tell", "chat"]
    assert world.unknown_codes == {}      # neither should count as unknown


def test_enemy_label_comes_from_aab():
    world, _, _ = drive([
        mip("12345", "AAB~Gabriel, archangel of Yesod {glowing} [scratched]"),
    ])
    assert world.enemy_label.startswith("Gabriel")


def test_a_code_that_stops_arriving_is_noticed():
    """Setting the look_* markers silenced HAA outright, which took the room's
    contents with it and left routes with nothing to attack.  Nothing
    announced it; the room panel simply emptied."""
    from mud.session import Session

    s = Session("127.0.0.1", 1, sec_code=12345)
    assert s.mip_quiet() == []                  # nothing seen yet, no claim

    for _ in range(5):
        s.codes_seen["DDD"] += 1
    s.codes_seen["HAB"] += 1
    assert s.mip_quiet() == ["HAA (room contents)"]

    s.codes_seen["HAA"] += 1
    assert s.mip_quiet() == []
