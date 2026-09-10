"""Hiding your own lines in the messages window.

"I want to see yours/other messages, not what I sent."  A tell says itself
which way it went; a channel line is yours when 3K names your character as its
speaker -- 22 of 510 channel records in the captures are the player's own.  So
the client has to know who is playing, including for somebody who typed their
name at 3K's own prompt rather than choosing it on the login screen -- and
must never take the line typed at the password prompt for a name.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.profile import Character  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"

NAME_PROMPT = (b"<Entering 3Kingdoms.  Enter your character name or press "
               b"enter to continue>")


class Wire:
    def write(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


def session() -> Session:
    s = Session(jumpstart=False,
                prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    s._writer = Wire()
    s.connected = True
    return s


def test_a_name_typed_at_the_prompt_is_who_is_playing():
    s = session()
    s._consume(NAME_PROMPT)
    s.send("Player")
    assert s.who_am_i == "Player"


def test_the_password_is_never_taken_for_a_name():
    s = session()
    s._consume(NAME_PROMPT)
    s.send("Player")
    s._consume(b"\r\nPassword: ")
    s.send("hunter2")                       # typed by hand, not marked secret
    assert s.who_am_i == "Player"
    assert s.me != "hunter2"


def test_nothing_typed_later_is_taken_for_a_name():
    s = session()
    s._consume(NAME_PROMPT + b"\r\nPassword: \r\nWelcome back.\r\n")
    s.send("say hello")
    assert s.who_am_i == ""


def test_a_character_chosen_on_the_login_screen_wins():
    s = session()
    s._consume(NAME_PROMPT)
    s.send("Typed")
    s.character = Character("Chosen")
    assert s.who_am_i == "Chosen"


def test_the_page_is_told_who_is_playing():
    s = session()
    s._consume(NAME_PROMPT)
    s.send("Player")
    assert WebServer(s).snapshot()["who"]["me"] == "Player"


def test_the_messages_window_can_hide_your_own_lines():
    js = (UI / "chat.js").read_text()
    assert "hideMine && isMine(m)" in js
    assert "store.set(`cm:${ID}:hidemine`" in js
    assert "window.setMe(s.who.me)" in (UI / "app.js").read_text()
