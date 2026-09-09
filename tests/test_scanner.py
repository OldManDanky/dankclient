"""Scanner tests, built from real 3k.org traffic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.scanner import Message, Scanner, Text  # noqa: E402

# --- real captures -----------------------------------------------------------

COMPOSITE = (
    b"#K%12345068FFFJ~G2N: <y81094877>    <cChi Focus>: <gNormal>    "
    b"<yAE>: <g14>/83%"
)

# two complete messages back to back, no separator, then ordinary room text
BACK_TO_BACK = (
    b"#K%12345003DDD"
    b"#K%12345083HAAnpc~Marble Monolith~A huge marble monolith~"
    b"exa #N/say hi, #N/consider #N/kill #N"
    b"-M-_A huge marble\nmonolith."
)

TELL = b"#K%12345014BABx~Buddy~moo"


def messages(events):
    return [e for e in events if isinstance(e, Message)]


def text(events):
    return b"".join(e.data for e in events if isinstance(e, Text))


def test_composite_frames_exactly():
    (msg,) = messages(Scanner().feed(COMPOSITE))
    assert msg.sec == "12345"
    assert msg.code == "FFF"
    # declared count is 68 and covers the 3-char code
    assert len(msg.code) + len(msg.data) == 68
    assert msg.data.startswith("J~G2N:")


def test_back_to_back_messages_and_trailing_text():
    events = Scanner().feed(BACK_TO_BACK)
    a, b = messages(events)

    assert (a.code, a.data) == ("DDD", "")          # count 003 == code only
    assert b.code == "HAA"
    assert len(b.code) + len(b.data) == 83

    fields = b.data.split("~")
    assert fields[0] == "npc"
    assert fields[1] == "Marble Monolith"
    assert fields[3].split("/") == [
        "exa #N", "say hi, #N", "consider #N", "kill #N",
    ]

    # everything past the 83rd byte is ordinary output, newline included
    assert text(events) == b"-M-_A huge marble\nmonolith."


def test_tell_fields():
    (msg,) = messages(Scanner().feed(TELL))
    assert msg.code == "BAB"
    assert msg.data.split("~") == ["x", "Buddy", "moo"]


def test_byte_at_a_time_is_identical():
    """The split-packet case: state must survive arbitrary fragmentation."""
    whole = messages(Scanner().feed(BACK_TO_BACK))

    drip = Scanner()
    got = []
    for i in range(len(BACK_TO_BACK)):
        got += messages(drip.feed(BACK_TO_BACK[i : i + 1]))

    assert got == whole


def test_every_split_point_agrees():
    whole = messages(Scanner().feed(BACK_TO_BACK))
    for cut in range(len(BACK_TO_BACK) + 1):
        s = Scanner()
        got = messages(s.feed(BACK_TO_BACK[:cut]))
        got += messages(s.feed(BACK_TO_BACK[cut:]))
        assert got == whole, f"disagreement when split at {cut}"


def test_literal_magic_in_chat_is_passed_through():
    """A player typing the activate literal must never desync the parser."""
    line = b"Buddy chats: try #K% or #K%abc or ##K%12 for fun\n"
    events = Scanner().feed(line)
    assert messages(events) == []
    assert text(events) == line


def test_short_count_is_rejected():
    """Counts below 3 are impossible -- the count always covers the code."""
    line = b"#K%12345002XX"
    events = Scanner().feed(line)
    assert messages(events) == []
    assert text(events) == line


def test_text_around_messages_is_preserved():
    raw = b"You are hit!\n" + TELL + b"\nYou flee.\n"
    events = Scanner().feed(raw)
    assert len(messages(events)) == 1
    # The newline after the message is the message's own: 3K puts each one on
    # a line by itself.  Passing it on printed a blank line into the terminal
    # for every message -- and the regen composites arrive twice a beat, for
    # ever, so the terminal quietly scrolled while nothing was happening.
    assert text(events) == b"You are hit!\nYou flee.\n"


def test_a_message_takes_its_own_line_ending_with_it():
    for ending in (b"\n", b"\r\n"):
        events = Scanner().feed(b"before\n" + TELL + ending + b"after\n")
        assert text(events) == b"before\nafter\n", ending


def test_only_one_line_ending_belongs_to_the_message():
    """A blank line the MUD actually sent is still a blank line."""
    events = Scanner().feed(TELL + b"\r\n\r\nstill here\n")
    assert text(events) == b"\r\nstill here\n"


def test_text_straight_after_a_message_is_untouched():
    """3K puts a channel line's colour code right up against the message."""
    events = Scanner().feed(TELL + b"\x1b[36m[Passerby disconnects]\r\n")
    assert text(events) == b"\x1b[36m[Passerby disconnects]\r\n"


def test_a_carriage_return_alone_after_a_message_is_given_back():
    events = Scanner().feed(TELL + b"\rnot a line ending")
    assert text(events) == b"\rnot a line ending"


def test_the_line_ending_can_arrive_in_the_next_read():
    s = Scanner()
    first = s.feed(b"before\n" + TELL + b"\r")
    assert not s.in_message, "nothing is held but the carriage return"
    second = s.feed(b"\nafter\n")
    assert text(first) + text(second) == b"before\nafter\n"


def test_partial_message_is_held_not_leaked():
    s = Scanner()
    events = s.feed(b"#K%12345068FFFJ~G2N: <y8109")
    assert messages(events) == []
    assert text(events) == b""      # nothing leaks while mid-message
    assert s.in_message
