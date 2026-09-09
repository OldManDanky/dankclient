"""The character settings that make 3K's output readable."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.prefixes import Hidden, Prefixes  # noqa: E402


def test_the_description_field_is_set_at_both_ends():
    """room_long is the one usually left blank and the one that matters: it
    is the description, and a field with two ends needs no guessing about
    where prose stops."""
    marks = Prefixes(Path(tempfile.mkdtemp()) / "prefixes.json")
    pairs = dict(marks.pairs)
    assert pairs["room_long_pref"] == "-D-_"
    assert pairs["room_long_suff"] == "-D-_"
    assert pairs["room_short_pref"] == pairs["room_short_suff"] == "-R-_"


def test_the_command_verb_is_data_not_code():
    """A guess about 3K's syntax is not good enough to compile in; correct it
    once in the file and it stays corrected."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prefixes.json"
        path.write_text(json.dumps({
            "verb": "set",
            "set": [["room_long_pref", "-D-_"], ["room_long_suff", "-D-_"]],
        }))
        marks = Prefixes(path)
        marks.after = []
        assert marks.commands() == ["set room_long_pref -D-_",
                                    "set room_long_suff -D-_"]


def test_a_broken_file_falls_back_to_the_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prefixes.json"
        path.write_text("{not json")
        assert dict(Prefixes(path).pairs)["room_long_pref"] == "-D-_"


def test_it_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prefixes.json"
        marks = Prefixes(path)
        marks.verb = "aset"
        marks.pairs = [("room_long_pref", "<D>")]
        marks.after = ["3klient HAA on"]
        marks.save()
        assert Prefixes(path).commands() == ["aset room_long_pref <D>",
                                             "3klient HAA on"]


def test_the_look_markers_are_not_asked_for_any_more():
    """Setting them stopped HAA arriving at all -- 3K treats the markers and
    the records as two ways of doing one job.  HAA is what tells a route the
    command the MUD accepts for a creature, and a marker on a line we were not
    reading is no trade for that."""
    marks = Prefixes("/nonexistent.json")
    names = dict(marks.pairs)
    assert not [n for n in names if n.startswith("look_")]
    assert "3klient HAA on" in marks.commands()
    # and the ones this client set are cleared again, because it set them
    assert any("look_monster_pref reset" in c for c in marks.commands())


# --- taking the markers back out ---------------------------------------------

MARKERS = ["-R-_", "-D-_", "-X-_"]


def scrub(chunks, markers=MARKERS, keep=()):
    """Feed the pieces through in order and return everything shown."""
    hide = Hidden(markers, keep)
    return b"".join(hide.feed(c) for c in chunks) + hide.flush()


def line_at_a_time(raw, markers=MARKERS, keep=()):
    """The same rules stated the slow, obvious way, over whole lines.

    The filter cannot work like this -- text arrives in whatever lengths the
    network hands over, and a prompt never ends in a newline -- but where the
    two disagree, this one is right.
    """
    marks = [m.encode() for m in sorted(set(markers), key=len, reverse=True)]
    names = [k.encode() for k in keep]
    out = []
    for line in raw.split(b"\n"):
        body = line.rstrip(b"\r")
        if not any(m in body for m in marks) or any(k in body for k in names):
            out.append(line)
            continue
        cut = body
        for m in marks:
            cut = cut.replace(m, b"")
        if not cut.strip():
            continue                          # the marker took the line
        out.append(cut + line[len(body):])
    return b"\n".join(out)


def test_a_marker_never_reaches_the_screen():
    """They are scaffolding for the parser.  A player who types `look` should
    not have to read around it."""
    line = b"-R-_A Dark Square (e,w,s,n)       -R-_  -1-O-@\r\n"
    assert scrub([line]) == b"A Dark Square (e,w,s,n)         -1-O-@\r\n"


def test_the_line_keeps_the_width_3k_drew_it_at():
    """The room title is padded to a fixed column and 3K's own map follows it.
    Taking eight characters of marker out puts the map back where it sat
    before the markers existed, rather than shifting it."""
    name = b"A Dark Square (e,w,s,n)"
    drawing = b"  -1-1-O-@-O      "                  # 3K's own map, 18 wide
    line = (b"-R-_" + name + b" " * (60 - len(name)) + b"-R-_"
            + drawing + b"\r\n")
    assert len(line) == 86 + 2                       # as 3K sends it
    assert len(scrub([line])) == 78 + 2              # as it read before
    assert scrub([line]).endswith(drawing + b"\r\n")


def test_a_marker_alone_on_its_line_takes_the_line_with_it():
    """room_long closes on a line of its own.  Removing just the text would
    leave a blank line where the description ends."""
    out = scrub([b"a room.\r\n-D-_\r\n    There are two exits.\r\n"])
    assert out == b"a room.\r\n    There are two exits.\r\n"


def test_two_marker_lines_running_together_both_go():
    out = scrub([b"a room.\r\n-D-_\r\n-D-_\r\nnext\r\n"])
    assert out == b"a room.\r\nnext\r\n"


def test_a_blank_line_the_mud_sent_is_a_blank_line():
    """The rule is that a marker takes its line with it, not that an empty
    line goes.  3K sends plenty of its own."""
    out = scrub([b"a room.\r\n\r\n-D-_and more\r\n"])
    assert out == b"a room.\r\n\r\nand more\r\n"


def test_3k_quoting_the_setting_back_keeps_its_marker():
    """It is the one line where the marker is the message.  Blanking it reads
    as the setting having failed, at the exact moment somebody is watching to
    see whether it worked."""
    said = b"Variable room_short_pref set to: -R-_\r\n"
    assert scrub([said], MARKERS, ["room_short_pref"]) == said


def test_it_keeps_it_even_when_the_line_arrives_in_pieces():
    """The name comes before the marker, but not always in the same read."""
    said = b"Variable room_short_pref set to: -R-_\r\n"
    for n in range(1, len(said) + 1):
        pieces = [said[i:i + n] for i in range(0, len(said), n)]
        assert scrub(pieces, MARKERS, ["room_short_pref"]) == said, n


def test_a_marker_split_across_reads_still_goes():
    """The stream arrives in whatever lengths the network hands over, not in
    lines, so a marker can straddle two of them."""
    whole = b"a room.\r\n-D-_\r\n-R-_Somewhere (n)-R-_\r\n"
    want = scrub([whole])
    for n in range(1, len(whole) + 1):
        pieces = [whole[i:i + n] for i in range(0, len(whole), n)]
        assert scrub(pieces) == want, f"split every {n} bytes"


def test_the_carriage_return_of_a_crlf_can_arrive_on_its_own():
    """It routinely does, ahead of the newline that would settle whether the
    marker had the line to itself.  Treated as settled, it leaves the blank
    line behind."""
    assert scrub([b"a room.\r\n-D-_\r", b"\nnext\r\n"]) == b"a room.\r\nnext\r\n"


def test_a_held_tail_is_shown_once_the_prompt_says_nothing_follows():
    """Text that merely starts like a marker must not wait on the network."""
    hide = Hidden(MARKERS)
    assert hide.feed(b"cost: 5-") == b"cost: 5"
    assert hide.flush() == b"-"


def test_a_marker_that_starts_with_another_still_goes_whole():
    """Shortest-first would eat the head and leave the tail on screen."""
    assert scrub([b"x-D-_zz y\r\n"], ["-D-", "-D-_z"]) == b"xz y\r\n"


def test_with_no_markers_the_stream_is_passed_straight_through():
    """A character with none set should cost nothing and change nothing."""
    raw = b"anything at all\r\n-D-_\r\n"
    assert scrub([raw], []) == raw


def test_a_whole_line_is_cleaned_for_the_log_and_for_triggers():
    """Triggers match what the player sees, and nobody searches the log for a
    marker."""
    hide = Hidden(MARKERS)
    assert hide.line("-X-_    There are two exits.-X-_") == "    There are two exits."
    assert hide.line("-D-_") == ""


TRANSCRIPT = (
    b"\x1b[36m3s: [somebody reconnects]\x1b[0m\r\n"
    b"\r\n"
    b"-R-_A Dark Square (e,w,s,n)                    -R-_  -1-O-@   \r\n"
    b"-D-_Chequered stone stretches away in both directions.\r\n"
    b"It is not clear which colour you are standing on.\r\n"
    b"-D-_\r\n"
    b"-X-_    There are four obvious exits: east, west, south, north  -X-_\r\n"
    b"#K%40142010DDDe~w~s~n\r\n"
    b"Variable room_short_pref set to: -R-_\r\n"
    b"\r\n"
    b"-D-_\r\n"
    b"-D-_\r\n"
    b"a line that merely mentions -D- and -R without finishing them\r\n"
    b">"
)


def test_however_it_is_cut_up_the_answer_is_the_same():
    """The network decides where the reads land, so the filter must not.
    Checked against the whole-line rules, which is what it is imitating."""
    keep = ["room_short_pref"]
    want = line_at_a_time(TRANSCRIPT, MARKERS, keep)
    assert scrub([TRANSCRIPT], MARKERS, keep) == want
    for n in range(1, len(TRANSCRIPT) + 1):
        pieces = [TRANSCRIPT[i:i + n] for i in range(0, len(TRANSCRIPT), n)]
        assert scrub(pieces, MARKERS, keep) == want, f"split every {n} bytes"


def test_the_prompt_is_not_held_back_waiting_for_a_newline():
    """It never gets one.  A client that waits for it shows nothing."""
    hide = Hidden(MARKERS, ["room_short_pref"])
    assert hide.feed(TRANSCRIPT).endswith(b"\r\n>")
