"""What a character calls their own gauges.

He set GP1/GP2 to PU/SPU, closed the client and came back to psi -- 3K's
own name for the guild's points.  Two faults in one line: the name was kept
in `localStorage`, which belongs to the browser rather than to the
character, and the MUD's name outranked the player's anyway.  A gauge's
name is per character because the guild is: the next character is in a
different one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.profile import Character, Characters  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


def make(tmp):
    session = Session("127.0.0.1", 1, sec_code=12345)
    chars = Characters(Path(tmp) / "profiles", Path(tmp) / "scripts")
    return session, chars, WebServer(session, characters=chars)


def test_renaming_a_gauge_keeps_it_with_the_character_it_was_set_on():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = chars.put(Character("Player"))
        web._login_op({"op": "label", "key": "gp1", "text": "PU"})
        web._login_op({"op": "label", "key": "gp2", "text": "SPU"})
        # On disk, not in the page: a fresh read of the file has them.
        again = Characters(Path(tmp) / "profiles")
        assert again.get("Player").labels == {"gp1": "PU", "gp2": "SPU"}


def test_the_screen_is_told_what_this_character_calls_them():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = chars.put(Character("Player", labels={"gp1": "PU"}))
        assert web._who()["own_labels"] == {"gp1": "PU"}
        # And the next character's are their own.
        session.character = chars.put(Character("Other"))
        assert web._who()["own_labels"] == {}


def test_clearing_a_name_gives_the_gauge_back_to_the_mud():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = chars.put(Character("Player", labels={"gp1": "PU"}))
        web._login_op({"op": "label", "key": "gp1", "text": "  "})
        assert chars.get("Player").labels == {}
        assert Characters(Path(tmp) / "profiles").get("Player").labels == {}


def test_a_gauge_nobody_has_is_not_written_into_the_file():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = chars.put(Character("Player"))
        web._login_op({"op": "label", "key": "wallet", "text": "gold"})
        assert chars.get("Player").labels == {}


def test_a_name_is_not_allowed_to_be_a_paragraph():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = chars.put(Character("Player"))
        web._login_op({"op": "label", "key": "gp1", "text": "x" * 200})
        assert len(chars.get("Player").labels["gp1"]) <= 12


def test_with_nobody_playing_it_says_so_rather_than_losing_the_name():
    with tempfile.TemporaryDirectory() as tmp:
        session, chars, web = make(tmp)
        session.character = None
        said = []
        web._reply_login = lambda text: said.append(text)
        web._login_op({"op": "label", "key": "gp1", "text": "PU"})
        assert said and "character" in said[0]
