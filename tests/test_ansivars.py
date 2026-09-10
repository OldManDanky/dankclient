"""The character's own colours, kept so they can be put back.

Somebody trying this client sets its markers on their character, and they stay
there when that person goes back to the client they had.  So the settings are
read first -- off 3K's `ansivars` help page, which draws each variable's name
in its own colours -- and kept per character.

The page below is 3K's real reply, from a capture.  Only its first forty lines
were ever seen; the second page is written to look like the first.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands  # noqa: E402
from mud.ansivars import AnsiVars, parse_line, touched  # noqa: E402
from mud.session import Session  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"
E = "\x1b"

PAGE_ONE = (
    b"\r\n  \x1b[31m::::::::::::::::::::::::::::::::::::::::::\x1b[0m\r\n"
    b"  \x1b[33;1m                            Topic: Ansivars      \x1b[0m\r\n\r\n"
    b"                              ANSI variables\r\n"
    b"::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::\r\n\r\n"
    b"The following configurable ansi variables are currently supported.  You\r\n"
    b"can set them individually as you see them.  If you experience color\r\n\r\n"
    b"\x1b[0marmour\x1b[0m           When your armour breaks\r\n"
    b"\x1b[34;1mattack\x1b[0m           Damage and hits that you do\r\n"
    b"attacked         Damage and hits done to you\r\n"
    b"\x1b[31mlook_monster\x1b[0m     Monsters you see\r\n"
    b"\x1b[35mlook_other\x1b[0m       Other things you see\r\n"
    b"hidemelee\x1b[0m            Other combat in the room\r\n"
    b"\x1b[0mroom_long\x1b[0m        The long description of rooms\r\n"
    b"\x1b[0mroom_short\x1b[0m       The short description of rooms\r\n"
    b"\x1b[32;1msoul\x1b[0m             All soul commands\r\n"
    b"soul2            Souls/emotes from mobs.\r\n"
    b"\x1b[7mtell\x1b[0m             Tells you send and receive\r\n"
    b"\x1b[36;1mMore: 0-39(42) : [q,b,<cr>] \x1b[0m")
PAGE_TWO = (b"\x1b[33mroom_exits\x1b[31m       The exits from a room\r\n"
            b"\x1b[31;1mwimpy\x1b[0m            When you run away/wimpy\r\n>\r\n")


class Wire:
    def __init__(self):
        self.lines = []

    def write(self, b):
        self.lines.append(b.decode("latin-1"))


def session(where=None):
    where = where or Path(tempfile.mkdtemp())
    s = Session(sec_code=12345, jumpstart=False,
                prefixes_path=str(where / "prefixes.json"))
    s._writer = Wire()
    return s


def read(s, *chunks):
    s.ask_ansivars()
    for chunk in chunks:
        s._consume(chunk)
    return s.finish_ansivars()


def test_the_colours_are_read_off_the_name():
    assert parse_line(f"{E}[34;1mattack{E}[0m           Damage") == (
        "attack", f"{E}[34;1m", f"{E}[0m")
    assert parse_line("attacked         Damage and hits done to you") == (
        "attacked", "", "")
    # A marker that ends in the same character a name can hold.
    assert parse_line(f"-M-_look_monster{E}[0m     Monsters") == (
        "look_monster", "-M-_", f"{E}[0m")
    assert parse_line(f"-i-look_other{E}[0m       Other")[:2] == ("look_other", "-i-")
    assert parse_line("soul2            Souls")[0] == "soul2"


def test_prose_and_rules_are_not_settings():
    for line in ("The following configurable ansi variables are currently.",
                 "::::::::::::::::::::::::::::::::::::::::::::",
                 "                              ANSI variables", ""):
        assert parse_line(line) is None, line


def test_the_real_page_is_read_and_its_pager_answered():
    s = session()
    snap = read(s, PAGE_ONE, PAGE_TWO)
    assert s._writer.lines == ["ansivars\r\n", "\r\n"], "Enter, once, at More"
    v = snap["vars"]
    assert v["tell"] == {"pref": f"{E}[7m", "suff": f"{E}[0m"}
    assert v["look_monster"]["pref"] == f"{E}[31m"
    assert v["attacked"] == {"pref": "", "suff": ""}
    # The first line after the pager arrives glued to its prompt.
    assert v["room_exits"] == {"pref": f"{E}[33m", "suff": f"{E}[31m"}
    assert "wimpy" in v and len(v) == 13


def test_it_is_kept_per_character_and_survives_a_restart():
    where = Path(tempfile.mkdtemp())
    read(session(where), PAGE_ONE, PAGE_TWO)
    again = session(where)
    assert (where / "ansivars.json").exists()
    assert again.ansivars.saved[-1]["vars"]["tell"]["pref"] == f"{E}[7m"


def test_putting_back_touches_only_what_this_client_changes():
    s = session()
    snap = read(s, PAGE_ONE, PAGE_TWO)
    sent = AnsiVars.restore(snap, touched(s.prefixes), s.prefixes.verb)
    assert f"aset room_exits_pref {E}[33m" in sent
    assert f"aset room_exits_suff {E}[31m" in sent
    assert "aset room_short reset" in sent and f"aset look_monster_pref {E}[31m" in sent
    assert not any("tell" in c or "attack" in c or "wimpy" in c for c in sent)


def test_a_reading_with_our_markers_in_it_is_not_one_to_go_back_to():
    """Somebody who already pressed Set ANSI prefixes and then saves has saved
    this client's markers; putting those back would change nothing."""
    s = session()
    ours = PAGE_ONE.replace(b"\x1b[0mroom_short\x1b[0m", b"-R-_room_short-R-_")
    read(s, ours, PAGE_TWO)
    assert s.ansivars.own(s.markers()) is None
    said = []
    commands.handle("/ansivars restore", s, None, said.append)
    assert "nothing saved from before" in said[0]
    read(s, PAGE_ONE, PAGE_TWO)
    assert s.ansivars.own(s.markers()) is s.ansivars.saved[-1]


def test_this_clients_old_look_markers_count_as_ours():
    """Its first pass set -M-_ and friends, which stopped HAA; a reading taken
    with them on would put that straight back."""
    s = session()
    read(s, PAGE_ONE.replace(b"\x1b[31mlook_monster", b"-M-_look_monster"), PAGE_TWO)
    assert s.ansivars.own(s.markers()) is None


def test_restore_shows_first_and_prints_no_escape():
    s = session()
    read(s, PAGE_ONE, PAGE_TWO)
    before = list(s._writer.lines)
    said = []
    commands.handle("/ansivars restore", s, None, said.append)
    assert "<ESC>[33m" in said[0] and E not in said[0]
    assert s._writer.lines == before, "nothing sent until confirmed"
    commands.handle("/ansivars restore go", s, None, said.append)
    # With room under the rate limit the queue sends at once.  The escape goes
    # as the byte itself, the way tt++ sends a \e -- not the text "<ESC>".
    assert f"aset room_exits_pref {E}[33m\r\n" in s._writer.lines[len(before):]


def test_nothing_on_the_page_saves_nothing():
    s = session()
    assert read(s, b"No such color vars.\r\n") is None
    assert s.ansivars.saved == [] and not s.ansivars.reading


def test_options_has_the_buttons():
    page = (UI / "index.html").read_text()
    js = (UI / "app.js").read_text()
    for element in ("ansi-save", "ansi-restore", "ansi-now"):
        assert f'id="{element}"' in page, element
    assert "'/ansivars'" in js and "'/ansivars restore'" in js
    assert "renderAnsivars(s.ansivars)" in js
