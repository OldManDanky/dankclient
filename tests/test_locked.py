"""Take updates beside a live session, without "database is locked".

A tester opened the bot list while an update ran and got "database is
locked".  The update merged the map in one transaction, holding the file for
as long as the merge took -- four seconds here, longer on a slower machine --
and the session's own writes, which wait five, gave up.  Reproduced with the
session's wait shortened below the merge's hold; fixed by importing in short
transactions, taking the write lock at the start of each, letting the
background update wait longer, and a log that keeps its lines rather than
losing them when the file is busy.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import tintin  # noqa: E402
from mud.logbook import Logbook  # noqa: E402
from mud.store import Store  # noqa: E402


def a_map(path: Path, rooms: int) -> Path:
    lines = []
    for v in range(1, rooms + 1):
        lines.append(f"R {{{v}}} {{0}} {{}} {{Room {v} (e,w)}} {{ }} {{}} {{Here}} "
                     "{} {} {} {1.000} {}")
        if v < rooms:
            lines.append(f"E {{{v + 1}}} {{e}} {{}} {{0}} {{0}} {{}} {{1.000}} {{}} {{0.00}}")
        if v > 1:
            lines.append(f"E {{{v - 1}}} {{w}} {{}} {{0}} {{0}} {{}} {{1.000}} {{}} {{0.00}}")
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    return path


def test_the_import_goes_in_short_transactions_that_lock_first():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(str(Path(tmp) / "map.sqlite"))
        said = []
        store.db.set_trace_callback(said.append)
        was = tintin.CHUNK
        tintin.CHUNK = 100
        try:
            did = tintin.import_map(store, a_map(Path(tmp) / "t.map", 450), merge=True)
        finally:
            tintin.CHUNK = was
        assert did["rooms"] == 450
        begins = [s for s in said if s.strip().upper().startswith("BEGIN")]
        assert len(begins) >= 10, "rooms and exits a piece at a time"
        assert all(b.strip().upper() == "BEGIN IMMEDIATE" for b in begins), \
            "every one takes the write lock at the start"


def test_the_log_keeps_its_lines_while_the_file_is_busy():
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "map.sqlite")
        store = Store(path, wait=0.1)
        book = Logbook(store)
        other = sqlite3.connect(path, isolation_level=None)
        other.execute("BEGIN IMMEDIATE")              # an update, mid-merge
        for n in range(5):
            book.add("recv", f"line {n}")
        book.flush()
        assert len(book) == 5, "kept, not lost"
        other.execute("COMMIT")
        book._hold_until = 0
        book.flush()
        assert len(book) == 0
        written = store.db.execute("SELECT count(*) FROM line").fetchone()[0]
        assert written == 5


def test_the_update_waits_longer_than_the_session():
    src = (Path(__file__).resolve().parents[1] / "mud" / "update.py").read_text()
    assert "Store(store_path, wait=60.0)" in src
    assert Store().db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
