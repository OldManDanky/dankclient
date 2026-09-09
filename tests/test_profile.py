"""Characters, and which settings follow one rather than the player."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.login import Login  # noqa: E402
from mud.profile import Character, Characters, activate  # noqa: E402


def chars(tmp, seed="scripts"):
    return Characters(Path(tmp) / "profiles", Path(tmp) / seed)


# --- the list ---------------------------------------------------------------

def test_a_character_gets_a_directory_of_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player"))
        assert c.rules_path("Player") != c.rules_path("Other")
        assert c.rules_path("Player").parent.name == "player"


def test_a_name_that_is_not_a_directory_name_still_gets_one():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        assert Character("Mad Jack O'Hare").slug == "mad-jack-o-hare"
        assert Character("../etc").slug == "etc"
        assert Character("   ").slug == "character"
        assert c.dir("../etc").parent == c.root      # never above the root


def test_the_list_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player", host="3k.org", port=3000, note="the mage"))
        again = chars(tmp)
        assert [x.name for x in again.all] == ["Player"]
        assert again.get("player").note == "the mage"      # asked for by name


def test_a_password_is_never_handed_to_the_browser():
    """The panel shows whether one is kept, never what it is -- so a saved
    password cannot leak through a snapshot, and cannot come back changed."""
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player", password="hunter2"))
        shown = c.public()[0]
        assert "password" not in shown
        assert shown["has_password"] is True
        assert "hunter2" not in json.dumps(c.public())


def test_the_file_holding_a_password_is_private():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player", password="hunter2"))
        mode = stat.S_IMODE(os.stat(c.path).st_mode)
        assert mode & 0o077 == 0, f"characters.json is {mode:o}"


def test_saving_without_a_password_keeps_the_one_already_there():
    """The browser is never sent the password, so it cannot send it back.  An
    empty box means "leave it alone", not "forget it"."""
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        c.put(Character("Player", password="hunter2"))
        c.put(Character("Player", note="edited"))
        assert c.get("Player").password == "hunter2"
        assert c.get("Player").note == "edited"


def test_settings_from_before_profiles_seed_the_first_character():
    """Somebody who has been using this client already has rules.  Their first
    character should start with them rather than with nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        shared = Path(tmp) / "scripts"
        shared.mkdir()
        (shared / "rules.json").write_text('[{"name": "old"}]')
        c = chars(tmp)
        assert json.loads(c.rules_path("Player").read_text())[0]["name"] == "old"
        # copied, not moved: the next character starts from the same place
        assert (shared / "rules.json").exists()
        assert json.loads(c.rules_path("Other").read_text())[0]["name"] == "old"


def test_one_characters_edits_do_not_reach_another():
    with tempfile.TemporaryDirectory() as tmp:
        shared = Path(tmp) / "scripts"
        shared.mkdir()
        (shared / "rules.json").write_text("[]")
        c = chars(tmp)
        c.rules_path("Player").write_text('[{"name": "mine"}]')
        assert json.loads(c.rules_path("Other").read_text()) == []


# --- switching --------------------------------------------------------------

class FakeRules:
    def __init__(self):
        self.path, self.loaded, self.registered = None, 0, 0

    def load(self):
        self.loaded += 1

    def register(self):
        self.registered += 1


class FakeScripts:
    def __init__(self):
        self.rules = FakeRules()


class FakeSession:
    def __init__(self):
        self.character, self.prefixes_at = None, None

    def reload_prefixes(self, path=None):
        self.prefixes_at = path


def test_choosing_a_character_moves_the_rules_and_the_markers_together():
    """Rules that outlive a profile switch are rules firing on the wrong
    character, which you notice by watching yourself cast a spell you do not
    have."""
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        char = c.put(Character("Player"))
        session, scripts = FakeSession(), FakeScripts()
        activate(char, c, session, scripts)
        assert session.character is char
        assert Path(session.prefixes_at).parent.name == "player"
        assert scripts.rules.path == c.rules_path("Player")
        assert (scripts.rules.loaded, scripts.rules.registered) == (1, 1)
        assert c.get("Player").last_played > 0


def test_it_works_with_scripting_switched_off():
    with tempfile.TemporaryDirectory() as tmp:
        c = chars(tmp)
        session = FakeSession()
        activate(c.put(Character("Player")), c, session, None)
        assert session.character.name == "Player"


# --- the two questions 3K asks ---------------------------------------------

PROMPT = ("<Entering 3Kingdoms.  Enter your character name or press enter "
          "to continue>")


def sent():
    out = []
    return out, (lambda text, secret=False: out.append((text, secret)))


def test_it_answers_both_questions():
    out, send = sent()
    login = Login(send)
    login.begin("Player", "hunter2")
    login.feed(PROMPT)
    login.feed("Password: ")
    assert out == [("Player", False), ("hunter2", True)]


def test_the_password_is_marked_so_it_is_never_written_down():
    out, send = sent()
    login = Login(send)
    login.begin("Player", "hunter2")
    login.feed(PROMPT + "Password: ")
    assert [secret for _, secret in out] == [False, True]


def test_a_prompt_already_on_screen_is_still_answered():
    """The connection is made at startup and the browser takes a moment to
    appear, so by the time you pick a name the question has been asked and
    nothing is going to ask it again."""
    out, send = sent()
    login = Login(send)
    login.feed(PROMPT)
    assert out == []
    login.begin("Player", "hunter2")
    assert out[0] == ("Player", False)


def test_the_name_prompt_does_not_answer_the_password_question():
    """They arrive within a few bytes of each other."""
    out, send = sent()
    login = Login(send)
    login.begin("Player", "hunter2")
    login.feed(PROMPT)
    assert len(out) == 1, "sent the name twice, or the password too early"


def test_a_prompt_split_across_reads_is_still_seen():
    whole = PROMPT + "\r\nPassword: "
    for n in range(1, 40):
        out, send = sent()
        login = Login(send)
        login.begin("Player", "hunter2")
        for i in range(0, len(whole), n):
            login.feed(whole[i:i + n])
        assert out == [("Player", False), ("hunter2", True)], f"in {n}s"


def test_with_no_password_it_sends_the_name_and_stops():
    """Better a prompt waiting for you than a name typed into a game that then
    sits on a password you never gave it."""
    out, send = sent()
    login = Login(send)
    login.begin("Player", "")
    login.feed(PROMPT + "Password: ")
    assert out == [("Player", False)]


def test_it_says_when_the_mud_is_still_asking():
    """Picking a character an hour into playing loads their rules; it must not
    type their name into the game."""
    out, send = sent()
    login = Login(send)
    assert not login.waiting
    login.feed(PROMPT)
    assert login.waiting
    login.begin("Player", "hunter2")
    login.feed("Password: ")
    assert not login.waiting and login.done


def test_skipping_stops_it_answering_anything():
    out, send = sent()
    login = Login(send)
    login.feed(PROMPT)
    login.cancel()
    assert not login.waiting and login.done
    login.feed("Password: ")
    assert out == []


# --- the one string that must not be written down ---------------------------

def test_a_password_reaches_the_socket_and_nowhere_else():
    """The capture exists to be replayed and shared; the log exists to be
    searched.  Neither is a place for a password."""
    import tempfile as tf
    from mud.capture import CaptureWriter, read_commands
    from mud.session import Session

    class Wire:
        def __init__(self):
            self.out = []

        def write(self, data):
            self.out.append(data)

    with tf.TemporaryDirectory() as tmp:
        log = CaptureWriter(Path(tmp) / "run")
        session = Session(raw_log=log)
        session._writer = Wire()
        session.login.begin("Player", "hunter2")
        session.login.feed(PROMPT + "Password: ")
        log.close()

        wire = b"".join(session._writer.out).decode("latin-1")
        assert "hunter2" in wire, "the MUD never got it"
        written = [line for _, line in read_commands(Path(tmp) / "run")]
        assert written == ["Player", "********"], written
