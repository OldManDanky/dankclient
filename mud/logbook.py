"""Everything the session saw, written where it can be searched later.

Lines arrive faster than anything wants to commit -- a busy Beloch party puts
three pages on screen per two-second round -- so they are buffered and written
in batches.  The buffer is small and the flush interval short, because the
point of a log is answering "what did they say ten minutes ago" and a session
that crashes should still be able to answer it.

Every line is stamped with the room the mapper believes you were standing in,
which turns the log from a transcript into something you can ask questions of:
what happened in the Temple of Hod, not just when.
"""

from __future__ import annotations

import sqlite3
import time

MAX_PENDING = 200
FLUSH_AFTER = 2.0
#: After a flush the file was too busy for, how long before trying again.
RETRY_AFTER = 2.0


class Logbook:
    def __init__(self, store, mapper=None, session_id: int | None = None) -> None:
        self.store = store
        self.mapper = mapper
        self.session_id = (store.begin_session() if session_id is None
                           else session_id)
        self._pending: list[tuple] = []
        self._last_flush = time.monotonic()
        #: not before this: the last flush found the file busy
        self._hold_until = 0.0

    def close(self) -> None:
        """Everything on disk, and the session marked finished.

        The buffer holds a few seconds of history, and a few seconds is still
        history -- it must not be the part you lose by leaving tidily.
        """
        self.flush()
        self.store.end_session(self.session_id)

    def reopen(self) -> None:
        """It did not finish after all: somebody pressed Reconnect."""
        self.store.reopen_session(self.session_id)

    def tail(self, limit: int = 400) -> list[dict]:
        """The last few lines of this session, oldest first.

        What the terminal puts back after a refresh.  The buffer has to be read
        as well as the table: it holds the newest few seconds, which is exactly
        the part you were looking at when you refreshed.
        """
        held = [{"kind": row[2], "text": row[6], "at": row[1]}
                for row in self._pending if row[2] in ("recv", "sent")]
        want = max(0, limit - len(held))
        rows = self.store.tail(self.session_id, want) if want else []
        return [{"kind": r["kind"], "text": r["text"], "at": r["at"]}
                for r in rows] + held[-limit:]

    def played_by(self, character: str) -> None:
        """Say who this session is.  The client is up and logging before
        anybody has picked a character, so it cannot be known any earlier."""
        self.store.name_session(self.session_id, character)

    def _where(self) -> int | None:
        return None if self.mapper is None else self.mapper.here

    def moved(self, room_id: int, since: float) -> None:
        """Re-stamp buffered lines with the room they actually describe.

        A room's text arrives *before* the MIP block that identifies it -- you
        read the description, then the client learns where you are -- so every
        line of an arrival would otherwise be filed under the room you just
        left.  Anything logged since the command that moved you belongs to the
        new room.

        Only what is still buffered can be corrected, which in practice is all
        of it: moves resolve in a tenth of a second and the buffer holds
        seconds.
        """
        for i, row in enumerate(self._pending):
            if row[1] >= since:
                self._pending[i] = (*row[:3], room_id, *row[4:])

    def add(self, kind: str, text: str, channel: str | None = None,
            who: str | None = None) -> None:
        if not text:
            return
        self._pending.append(
            (self.session_id, time.time(), kind, self._where(), channel, who,
             text)
        )
        now = time.monotonic()
        if now < self._hold_until:
            return
        if (len(self._pending) >= MAX_PENDING
                or now - self._last_flush >= FLUSH_AFTER):
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            self._last_flush = time.monotonic()
            return
        rows, self._pending = self._pending, []
        self._last_flush = time.monotonic()
        db = self.store.db
        try:
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            # Somebody else is writing -- Take updates, merging the map.  The
            # lines are kept and tried again shortly: losing them, or stopping
            # the session over it, would both be worse than waiting.
            self._pending = rows + self._pending
            self._hold_until = time.monotonic() + RETRY_AFTER
            return
        try:
            for row in rows:
                cur = db.execute(
                    "INSERT INTO line (session_id, at, kind, room_id, channel, "
                    "who, text) VALUES (?,?,?,?,?,?,?)", row
                )
                db.execute("INSERT INTO line_fts (rowid, text) VALUES (?,?)",
                           (cur.lastrowid, row[-1]))
            db.execute("COMMIT")
        except sqlite3.OperationalError:
            db.execute("ROLLBACK")
            self._pending = rows + self._pending
            self._hold_until = time.monotonic() + RETRY_AFTER
        except Exception:
            db.execute("ROLLBACK")
            raise

    def __len__(self) -> int:
        return len(self._pending)
