"""What the session saw, written where it can be searched."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.logbook import Logbook  # noqa: E402
from mud.store import Store  # noqa: E402


class FakeWriter:
    def write(self, data): pass


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


def session_with_store():
    from mud.session import Session

    store = Store()
    s = Session("127.0.0.1", 1, sec_code=12345, store=store)
    s._writer = FakeWriter()
    return s, store


def test_lines_are_buffered_until_there_are_enough_of_them():
    """A Beloch party puts three pages on screen per round; committing each
    line as it lands would spend the session in SQLite."""
    store = Store()
    book = Logbook(store)
    book.add("recv", "one")
    book.add("recv", "two")
    assert len(book) == 2
    assert store.db.execute("SELECT COUNT(*) c FROM line").fetchone()["c"] == 0
    book.flush()
    assert store.db.execute("SELECT COUNT(*) c FROM line").fetchone()["c"] == 2


def test_both_halves_of_the_session_are_logged():
    s, store = session_with_store()
    s._consume(b"Michael raises his arms.\r\n")
    s.send("kill michael")
    s.logbook.flush()

    kinds = {r["kind"]: r["text"] for r in store.db.execute("SELECT * FROM line")}
    assert kinds["recv"] == "Michael raises his arms."
    assert kinds["sent"] == "kill michael"


def test_colour_is_stripped_before_it_reaches_the_index():
    """Nobody searches for an escape sequence, and the codes would swamp the
    index with noise."""
    s, store = session_with_store()
    s._consume(b"\x1b[31;1mSandalphon hits you\x1b[0m\r\n")
    s.logbook.flush()
    assert store.search("Sandalphon")[0]["text"] == "Sandalphon hits you"


def test_tells_and_channels_are_logged_as_themselves():
    """Not only as raw output: 'everything Someone said' should be one query,
    not a guess at how the MUD worded it."""
    s, store = session_with_store()
    s._consume(mip("CAA", "shout~Shout~Someone~Someone shouts: that spam stinks"))
    s._consume(mip("BAB", "~Buddy~moos at you."))
    s.logbook.flush()

    chat = store.search("spam", kind="chat")
    assert chat and chat[0]["who"] == "Someone" and chat[0]["channel"] == "Shout"
    assert store.search("moos", kind="tell")[0]["who"] == "Buddy"


def test_a_line_remembers_which_room_you_were_in():
    """'What happened in the Temple of Hod' is the question a transcript
    cannot answer and this can."""
    s, store = session_with_store()
    s._consume(mip("DDD", "n") + mip("HAB", "noun~sky~sky~exa #N"))
    s._consume(mip("FFF", "A~100"))               # settles the room block
    s._consume(b"Something happens here.\r\n")
    s.logbook.flush()

    line = store.search("happens")[0]
    assert line["room_id"] == s.mapper.here


def test_searching_finds_a_phrase_across_kinds():
    s, store = session_with_store()
    s._consume(b"you sense a beloch nearby\r\n")
    s.send("kill beloch")
    s.logbook.flush()
    assert len(store.search("beloch")) == 2
    assert store.context(store.search("beloch")[0]["id"], before=1, after=1)


def test_an_arrivals_description_is_filed_under_the_room_it_describes():
    """The MUD prints the room, then MIP says which room it was.  Logged as
    they arrive, every line of an arrival lands under the room you just left --
    which is exactly backwards for "what happened in the Temple of Hod"."""
    s, store = session_with_store()

    s._consume(mip("DDD", "n") + mip("HAB", "noun~sky~sky~exa #N"))
    s._consume(mip("FFF", "A~100"))
    first = s.mapper.here

    s.send("n")
    s._consume(b"North lane\r\nThere are three obvious exits.\r\n")
    s._consume(mip("DDD", "s~e") + mip("HAB", "noun~wall~wall~exa #N"))
    s._consume(mip("FFF", "A~99"))
    second = s.mapper.here
    s.logbook.flush()

    assert second != first
    where = {r["text"]: r["room_id"] for r in store.db.execute(
        "SELECT text, room_id FROM line WHERE kind = 'recv'")}
    assert where["North lane"] == second
    assert where["There are three obvious exits."] == second


def test_lines_from_before_the_move_keep_their_room():
    s, store = session_with_store()
    s._consume(mip("DDD", "n") + mip("HAB", "noun~sky~sky~exa #N"))
    s._consume(mip("FFF", "A~100"))
    first = s.mapper.here

    s._consume(b"A tall street light.\r\n")     # standing still, before any move
    s.send("n")
    s._consume(mip("DDD", "s") + mip("HAB", "noun~wall~wall~exa #N"))
    s._consume(mip("FFF", "A~99"))
    s.logbook.flush()

    row = store.search("street light")[0]
    assert row["room_id"] == first


# --- what the terminal puts back ---------------------------------------------

def test_the_tail_reads_the_buffer_as_well_as_the_table():
    """The buffer holds the newest few seconds -- which is exactly the part you
    were looking at when you refreshed, so it cannot be skipped."""
    store = Store()
    book = Logbook(store)
    for i in range(5):
        book.add("recv", f"line {i}")
    assert [l["text"] for l in book.tail()] == [f"line {i}" for i in range(5)]

    book.flush()                       # same answer once it is on disk
    assert [l["text"] for l in book.tail()] == [f"line {i}" for i in range(5)]

    book.add("recv", "line 5")         # and across the join
    assert [l["text"] for l in book.tail()] == [f"line {i}" for i in range(6)]


def test_the_tail_is_oldest_first_and_bounded():
    store = Store()
    book = Logbook(store)
    for i in range(50):
        book.add("recv", f"line {i}")
    book.flush()
    got = [l["text"] for l in book.tail(10)]
    assert got == [f"line {i}" for i in range(40, 50)], got


def test_the_tail_is_the_terminal_not_the_channels():
    """Tells and chat have their own window and are seeded into it separately;
    replaying them here would put a second copy in the terminal."""
    store = Store()
    book = Logbook(store)
    book.add("recv", "you are here")
    book.add("chat", "[Clan] Friend : moo", channel="Clan Sa", who="Friend")
    book.add("sent", "look")
    book.flush()
    assert [l["kind"] for l in book.tail()] == ["recv", "sent"]


def test_one_session_does_not_replay_another():
    store = Store()
    old = Logbook(store)
    old.add("recv", "yesterday")
    old.flush()
    new = Logbook(store)
    new.add("recv", "today")
    assert [l["text"] for l in new.tail()] == ["today"]
