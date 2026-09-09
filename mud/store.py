"""On-disk memory: the map, and everything the session saw.

One SQLite file holds both because they answer each other's questions -- "what
did someone say about Belochs" and "where was I standing when they said it" are the
same lookup with a different column.

Three rules are baked into the schema, and each one cost a wrong guess to find:

*Nothing here identifies a room.*  A room's id is assigned by the mapper from
its position in the graph; the name, the exits and the scenery are evidence
about a room, never the thing that makes it itself.  ``BAD`` names fewer than
half of all room entries, exit sets repeat across a whole chessboard, and the
scenery picks up nouns from whatever someone dropped on the floor.

*A room looks different from visit to visit,* so every fingerprint variant is
kept and counted rather than overwritten.  Matching is best-overlap, and the
evidence improves with visits instead of thrashing.

*One command can have more than one destination.*  Random exits and doors that
move exist, so the primary key spans the destination too; the mapper picks the
likeliest by count instead of the schema silently forgetting the alternative.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA_VERSION = 5

_SCHEMA = """
CREATE TABLE session (
    id         INTEGER PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at   REAL,                     -- null while running, or if it died
    capture    TEXT,                     -- stem of the .bin/.idx/.out on disk
    character  TEXT
);

CREATE TABLE region (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    parent_id INTEGER REFERENCES region(id) ON DELETE SET NULL,
    -- 'grid' lays rooms out by compass direction; 'blob' is for mazes and
    -- anywhere else coordinates would be a lie.
    layout    TEXT NOT NULL DEFAULT 'grid'
);
CREATE INDEX region_parent ON region(parent_id);

CREATE TABLE room (
    id         INTEGER PRIMARY KEY,
    name       TEXT,                     -- often unknown; never an identity
    region_id  INTEGER REFERENCES region(id) ON DELETE SET NULL,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    visits     INTEGER NOT NULL DEFAULT 0,
    note       TEXT
);
CREATE INDEX room_region ON room(region_id);
CREATE INDEX room_name ON room(name);

CREATE TABLE fingerprint (
    room_id  INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    exits    TEXT NOT NULL,              -- sorted, comma separated
    scenery  TEXT NOT NULL,              -- sorted, comma separated
    seen     INTEGER NOT NULL DEFAULT 0,
    last_seen REAL NOT NULL,
    PRIMARY KEY (room_id, exits, scenery)
) WITHOUT ROWID;
-- relocation searches by what the room looked like, so this is the hot index
CREATE INDEX fingerprint_lookup ON fingerprint(exits);

CREATE TABLE edge (
    from_room INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    command   TEXT NOT NULL,             -- "n", but also "climb pipe"
    to_room   INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    seen      INTEGER NOT NULL DEFAULT 0,
    -- Times this was walked and nothing happened.  An imported map is a
    -- hypothesis: it holds commands that have stopped working, personal
    -- shortcuts somebody else cannot type, doors that are now locked.  No
    -- inspection tells them apart, so walking is what finds out.
    failed    INTEGER NOT NULL DEFAULT 0,
    last_seen REAL NOT NULL,
    PRIMARY KEY (from_room, command, to_room)
) WITHOUT ROWID;
CREATE INDEX edge_to ON edge(to_room);

CREATE TABLE room_tag (
    room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    PRIMARY KEY (room_id, tag)
) WITHOUT ROWID;
CREATE INDEX room_tag_tag ON room_tag(tag);

-- Facts about this map rather than about the world: whether it was imported,
-- whether it may grow.  Small enough that a table beats a settings file, and
-- it travels with the map it describes.
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;

-- Named destinations: "go beloch".  A tt++ speedrun list is one of
-- these per line, and the names are what he already types.
CREATE TABLE landmark (
    name    TEXT PRIMARY KEY,
    room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    kind    TEXT,
    note    TEXT
) WITHOUT ROWID;
CREATE INDEX landmark_room ON landmark(room_id);

CREATE TABLE line (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    at         REAL NOT NULL,
    kind       TEXT NOT NULL,            -- recv | sent | tell | chat
    room_id    INTEGER REFERENCES room(id) ON DELETE SET NULL,
    channel    TEXT,
    who        TEXT,
    text       TEXT NOT NULL
);
CREATE INDEX line_at ON line(at);
CREATE INDEX line_kind ON line(kind, at);
CREATE INDEX line_room ON line(room_id, at);

-- External content: the text lives in `line`, the index only points at it.
CREATE VIRTUAL TABLE line_fts USING fts5(text, content='line', content_rowid='id');
"""


#: Applied in order to bring an older file up to date.  A map is months of
#: walking, so it is upgraded rather than thrown away.
_UPGRADES = {
    5: """
        ALTER TABLE session ADD COLUMN ended_at REAL;
    """,
    4: """
        ALTER TABLE edge ADD COLUMN failed INTEGER NOT NULL DEFAULT 0;
    """,
    3: """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID;
    """,
    2: """
        CREATE TABLE landmark (
            name    TEXT PRIMARY KEY,
            room_id INTEGER NOT NULL REFERENCES room(id) ON DELETE CASCADE,
            kind    TEXT,
            note    TEXT
        ) WITHOUT ROWID;
        CREATE INDEX landmark_room ON landmark(room_id);
    """,
}


class Store:
    """The map and the log.  Safe to open on a path that does not exist yet."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            # Readers (a search, the map panel) must not block the session
            # writing to the log mid-fight.
            self.db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        have = self.db.execute("PRAGMA user_version").fetchone()[0]
        if have == SCHEMA_VERSION:
            return
        if have == 0:
            self.db.executescript(_SCHEMA)
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return
        if have < SCHEMA_VERSION:
            for version in range(have + 1, SCHEMA_VERSION + 1):
                self.db.executescript(_UPGRADES[version])
                self.db.execute(f"PRAGMA user_version = {version}")
            return
        raise RuntimeError(
            f"map database is schema v{have}, this client speaks "
            f"v{SCHEMA_VERSION}; move {self.path} aside to start fresh"
        )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- what kind of map this is -------------------------------------------

    def setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?",
                              (key,)).fetchone()
        return default if row is None else row["value"]

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                        (key, value))

    @property
    def locked(self) -> bool:
        """May the map grow?

        An imported map is somebody's years of walking, complete enough that a
        room it does not contain is far more likely to be a room we failed to
        recognise.  Inventing one then is worse than admitting we are lost: it
        adds a duplicate of a room that is already there, and nothing later
        joins them up.
        """
        return self.setting("locked") == "1"

    @locked.setter
    def locked(self, value: bool) -> None:
        self.set_setting("locked", "1" if value else "")

    def clean_exits(self) -> int:
        """Take macros back out of rooms' exit lists.

        An earlier backfill took a room's exits from its edges without asking
        whether they were exits: "#15 hack east; east;" is a way somebody
        recorded of leaving a room, and DDD will never report it.  A room
        carrying one can still be recognised -- checking accepts a subset --
        but it can no longer be identified from a standing start, because that
        comparison is exact.
        """
        rows = self.db.execute(
            "SELECT room_id, exits, scenery FROM fingerprint "
            "WHERE exits LIKE '%;%'").fetchall()
        fixed = 0
        self.db.execute("BEGIN")
        try:
            for row in rows:
                kept = [e for e in row["exits"].split(",") if e and ";" not in e]
                self.db.execute(
                    "DELETE FROM fingerprint WHERE room_id = ? AND exits = ? "
                    "AND scenery = ?",
                    (row["room_id"], row["exits"], row["scenery"]))
                self.db.execute(
                    "INSERT OR REPLACE INTO fingerprint "
                    "(room_id, exits, scenery, seen, last_seen) "
                    "VALUES (?,?,?,0,?)",
                    (row["room_id"], ",".join(sorted(kept)), row["scenery"],
                     time.time()))
                fixed += 1
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return fixed

    def clean_edge_commands(self, translate) -> int:
        """Take the tt++ out of exits that already carry it.

        The importer does this on the way in now, but a map imported before it
        did keeps four hundred and sixty-nine of them, and every one is a
        command this client would type into the game.  Two exits can clean to
        the same thing -- "#31 climb" and "#31 climb;" -- so the cleaned one is
        added and the old one dropped, rather than renamed onto a key that may
        already exist.
        """
        rows = self.db.execute(
            "SELECT from_room, command, to_room, seen, failed, last_seen "
            "FROM edge WHERE command LIKE '%#%'").fetchall()
        fixed = 0
        self.db.execute("BEGIN")
        try:
            for row in rows:
                clean = translate(row["command"])
                if clean == row["command"]:
                    continue
                if clean:
                    self.db.execute(
                        "INSERT OR IGNORE INTO edge (from_room, command, "
                        "to_room, seen, failed, last_seen) VALUES (?,?,?,?,?,?)",
                        (row["from_room"], clean, row["to_room"], row["seen"],
                         row["failed"], row["last_seen"]))
                self.db.execute(
                    "DELETE FROM edge WHERE from_room = ? AND command = ? "
                    "AND to_room = ?",
                    (row["from_room"], row["command"], row["to_room"]))
                fixed += 1
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return fixed

    def fold_spaced_exits(self) -> int:
        """Collapse exits that are the same way out written differently.

        tt++ writes "search;open trapdoor; stairs" with a space after the
        semicolon, and for a while the importer rebuilt the string without it.
        That is a different string and therefore a different exit, so a map
        that already held the spaced one ended up with both -- 136 of them,
        every pair the same way out of the same room to the same place.

        The one that has been walked is kept, because that is the one carrying
        evidence; otherwise the longer spelling, which is the one tt++ wrote.
        """
        seen: dict[tuple[int, str, int], list] = {}
        for row in self.db.execute(
                "SELECT from_room, command, to_room, seen FROM edge").fetchall():
            flat = ";".join(part.strip()
                            for part in str(row["command"]).split(";")
                            if part.strip())
            seen.setdefault((row["from_room"], flat, row["to_room"]), []).append(row)

        dropped = 0
        self.db.execute("BEGIN")
        try:
            for rows in seen.values():
                if len(rows) < 2:
                    continue
                rows.sort(key=lambda r: (r["seen"], len(r["command"])),
                          reverse=True)
                for row in rows[1:]:
                    self.db.execute(
                        "DELETE FROM edge WHERE from_room = ? AND command = ? "
                        "AND to_room = ?",
                        (row["from_room"], row["command"], row["to_room"]))
                    dropped += 1
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return dropped

    def backfill_exits(self) -> int:
        """Give rooms their exits when tt++ recorded none in the title.

        5.2% of one real map is like this, and almost all of them have edges
        -- the ways out were mapped, they just never made it into the room's
        name.  Without this they can never match a live room, because the
        exits MIP sends will not equal an empty list.
        """
        rows = self.db.execute(
            "SELECT f.room_id AS id FROM fingerprint f WHERE f.exits = '' "
            "AND EXISTS (SELECT 1 FROM edge e WHERE e.from_room = f.room_id)"
        ).fetchall()
        fixed = 0
        self.db.execute("BEGIN")
        try:
            for row in rows:
                rid = int(row["id"])
                # Only things DDD could plausibly report.  An edge may be a
                # macro somebody recorded -- "search;open trapdoor; stairs" --
                # and that is a way to leave the room, not an exit it lists.
                exits = sorted({str(e["command"]).lower()
                                for e in self.exits_from(rid)
                                if ";" not in e["command"]})
                if not exits:
                    continue
                filled = ",".join(exits)
                # The room may already know what it looks like -- from walking
                # in, or from an earlier backfill -- and renaming the blank row
                # onto that one collides on the primary key.  This used to run
                # only against a map with nothing in it; a merge is the case
                # where both rows exist.  The blank is the one to drop, and the
                # one that is already there is the one to keep: it may have
                # been seen, and the backfilled row never has.
                for blank in self.db.execute(
                        "SELECT scenery FROM fingerprint "
                        "WHERE room_id = ? AND exits = ''", (rid,)).fetchall():
                    scenery = blank["scenery"]
                    already = self.db.execute(
                        "SELECT 1 FROM fingerprint WHERE room_id = ? "
                        "AND exits = ? AND scenery = ?",
                        (rid, filled, scenery)).fetchone()
                    if already:
                        self.db.execute(
                            "DELETE FROM fingerprint WHERE room_id = ? "
                            "AND exits = '' AND scenery = ?", (rid, scenery))
                    else:
                        self.db.execute(
                            "UPDATE fingerprint SET exits = ? WHERE room_id = ? "
                            "AND exits = '' AND scenery = ?",
                            (filled, rid, scenery))
                fixed += 1
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return fixed

    # --- sessions -----------------------------------------------------------

    def begin_session(self, capture: str | None = None,
                      character: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO session (started_at, capture, character) VALUES (?,?,?)",
            (time.time(), capture, character),
        )
        return int(cur.lastrowid)

    def end_session(self, session_id: int | None) -> None:
        """Say the session finished tidily.

        A row with no end never did: the client was killed, or it link-died and
        nobody brought it back.  Worth being able to tell apart afterwards --
        the interesting captures are usually the ones that end badly.
        """
        if session_id is None:
            return
        self.db.execute("UPDATE session SET ended_at = ? WHERE id = ?",
                        (time.time(), session_id))
        self.db.commit()

    def reopen_session(self, session_id: int | None) -> None:
        """...and it did not, because somebody pressed Reconnect."""
        if session_id is None:
            return
        self.db.execute("UPDATE session SET ended_at = NULL WHERE id = ?",
                        (session_id,))
        self.db.commit()

    def name_session(self, session_id: int | None, character: str) -> None:
        """Who was playing.  Not known when the row is made: the client is up
        and logging before anybody has said which character this is."""
        if session_id is None or not character:
            return
        self.db.execute("UPDATE session SET character = ? WHERE id = ?",
                        (character, session_id))
        self.db.commit()

    # --- rooms --------------------------------------------------------------

    def add_room(self, name: str | None = None, at: float | None = None) -> int:
        now = time.time() if at is None else at
        cur = self.db.execute(
            "INSERT INTO room (name, first_seen, last_seen, visits) "
            "VALUES (?,?,?,0)",
            (name, now, now),
        )
        return int(cur.lastrowid)

    def visit(self, room_id: int, name: str | None = None,
              at: float | None = None) -> None:
        """Record arriving.  A name only ever fills a blank or replaces itself;
        the MUD names a room inconsistently and the last word should not win."""
        now = time.time() if at is None else at
        self.db.execute(
            "UPDATE room SET visits = visits + 1, last_seen = ?, "
            "name = COALESCE(name, ?) WHERE id = ?",
            (now, name, room_id),
        )

    def suggest_name(self, room_id: int, name: str | None) -> None:
        """Fill a blank name.  Never replaces one: the MUD names rooms
        inconsistently and the most recent spelling should not simply win."""
        if name:
            self.db.execute(
                "UPDATE room SET name = COALESCE(name, ?) WHERE id = ?",
                (name, room_id),
            )

    def rename(self, room_id: int, name: str | None) -> None:
        self.db.execute("UPDATE room SET name = ? WHERE id = ?", (name, room_id))

    def prune_fingerprints(self, ratio: int = 5) -> list[tuple[int, str]]:
        """Drop one-off observations that contradict what a room usually is.

        A room's exits do not change.  When one carries two different exit
        lists and one of them was seen once against a dozen, that reading was
        somebody else's room written onto this one.  Scenery drifts and is
        left alone; only whole exit lists are judged, and only when the
        evidence is lopsided.
        """
        removed = []
        for row in self.db.execute(
            "SELECT room_id FROM fingerprint GROUP BY room_id "
            "HAVING COUNT(DISTINCT exits) > 1"
        ).fetchall():
            rid = int(row["room_id"])
            counts = self.db.execute(
                "SELECT exits, SUM(seen) n FROM fingerprint WHERE room_id = ? "
                "GROUP BY exits ORDER BY n DESC", (rid,)
            ).fetchall()
            best = counts[0]["n"]
            for other in counts[1:]:
                if other["n"] * ratio <= best:
                    self.db.execute(
                        "DELETE FROM fingerprint WHERE room_id = ? AND exits = ?",
                        (rid, other["exits"]),
                    )
                    removed.append((rid, other["exits"]))
        return removed

    def duplicates(self) -> list[tuple[str, list[int]]]:
        """Rooms that look like the same place twice.

        Grouped by exits and scenery together, because dead reckoning splits a
        room whenever a move goes unseen and nothing later rejoins the halves.
        A suggestion for a person to judge -- 3K really does have two Alchemy
        rows -- not something to act on automatically.
        """
        groups: dict[tuple[str, str], list[int]] = {}
        for row in self.db.execute(
            "SELECT room_id, exits, scenery FROM fingerprint "
            "WHERE scenery != '' ORDER BY seen DESC"
        ):
            key = (row["exits"], row["scenery"])
            ids = groups.setdefault(key, [])
            if row["room_id"] not in ids:
                ids.append(int(row["room_id"]))
        return [(f"{ex} | {sc}", ids)
                for (ex, sc), ids in groups.items() if len(ids) > 1]

    def tag(self, room_id: int, tag: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO room_tag (room_id, tag) VALUES (?,?)",
            (room_id, tag))

    def tagged(self, tag: str) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT r.* FROM room r JOIN room_tag t ON t.room_id = r.id "
            "WHERE t.tag = ? ORDER BY r.id", (tag,)))

    def merge(self, keep: int, drop: int) -> None:
        """Fold one room into another.

        Dead reckoning splits a room in two whenever a move goes unseen -- a
        laggy arrival, a command the MUD ate -- and nothing later rejoins them,
        because to the map they are simply two places.  Merging moves every
        edge and every observation onto the survivor and drops the duplicate.
        """
        if keep == drop:
            return
        db = self.db
        db.execute("BEGIN")
        try:
            for column in ("from_room", "to_room"):
                for row in db.execute(
                    f"SELECT * FROM edge WHERE {column} = ?", (drop,)
                ).fetchall():
                    src = keep if column == "from_room" else row["from_room"]
                    dst = keep if column == "to_room" else row["to_room"]
                    db.execute(
                        "INSERT INTO edge (from_room, command, to_room, seen, "
                        "last_seen) VALUES (?,?,?,?,?) "
                        "ON CONFLICT(from_room, command, to_room) DO UPDATE SET "
                        "seen = seen + excluded.seen, "
                        "last_seen = MAX(last_seen, excluded.last_seen)",
                        (src, row["command"], dst, row["seen"], row["last_seen"]),
                    )
            db.execute("DELETE FROM edge WHERE from_room = ? OR to_room = ?",
                       (drop, drop))
            for row in db.execute(
                "SELECT * FROM fingerprint WHERE room_id = ?", (drop,)
            ).fetchall():
                db.execute(
                    "INSERT INTO fingerprint (room_id, exits, scenery, seen, "
                    "last_seen) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(room_id, exits, scenery) DO UPDATE SET "
                    "seen = seen + excluded.seen, "
                    "last_seen = MAX(last_seen, excluded.last_seen)",
                    (keep, row["exits"], row["scenery"], row["seen"],
                     row["last_seen"]),
                )
            db.execute(
                "UPDATE room SET visits = visits + "
                "(SELECT visits FROM room WHERE id = ?), "
                "name = COALESCE(name, (SELECT name FROM room WHERE id = ?)) "
                "WHERE id = ?", (drop, drop, keep),
            )
            # The log points at rooms too; a merged-away room would leave
            # history stranded on an id that no longer exists.
            db.execute("UPDATE line SET room_id = ? WHERE room_id = ?",
                       (keep, drop))
            db.execute("DELETE FROM room WHERE id = ?", (drop,))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        # A room that now leads to itself is the usual result of merging the
        # two halves of one place, and a self-loop is never a real exit.
        self.db.execute("DELETE FROM edge WHERE from_room = to_room "
                        "AND from_room = ?", (keep,))

    def forget(self, room_id: int) -> None:
        """Remove a room the map should never have invented."""
        self.db.execute("DELETE FROM room WHERE id = ?", (room_id,))

    def room(self, room_id: int) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM room WHERE id = ?", (room_id,)
        ).fetchone()

    # --- fingerprints -------------------------------------------------------

    @staticmethod
    def fingerprint(exits: Iterable[str], scenery: Iterable[str]) -> tuple[str, str]:
        """Items are deliberately absent: coins, corpses and dropped clothes
        turned up in a third of the observed rooms and identify nothing."""
        return (
            ",".join(sorted(set(e.lower() for e in exits))),
            ",".join(sorted(set(s.lower() for s in scenery))),
        )

    def observe(self, room_id: int, exits: Iterable[str],
                scenery: Iterable[str], at: float | None = None) -> None:
        now = time.time() if at is None else at
        ex, sc = self.fingerprint(exits, scenery)
        self.db.execute(
            "INSERT INTO fingerprint (room_id, exits, scenery, seen, last_seen) "
            "VALUES (?,?,?,1,?) "
            "ON CONFLICT(room_id, exits, scenery) DO UPDATE SET "
            "seen = seen + 1, last_seen = excluded.last_seen",
            (room_id, ex, sc, now),
        )

    def exits_of(self, room_id: int) -> list[str]:
        """What the MUD last said this room's exits were.

        Distinct from the edges: DDD lists every way out, while an edge only
        exists once you have actually walked one.  The difference is the set
        of ways you have never taken.
        """
        row = self.db.execute(
            "SELECT exits FROM fingerprint WHERE room_id = ? "
            "ORDER BY seen DESC, last_seen DESC LIMIT 1", (room_id,)
        ).fetchone()
        return [] if row is None else [e for e in row["exits"].split(",") if e]

    def candidates(self, exits: Iterable[str],
                   scenery: Iterable[str]) -> list[tuple[int, float]]:
        """Rooms that could be this one, best first, for relocation.

        Scored on scenery overlap because scenery drifts -- weather nouns come
        and go, and a dropped item can register one -- so equality would reject
        the right room.  Exits have to match: they are what the MUD computes.
        """
        ex, sc = self.fingerprint(exits, scenery)
        want = set(sc.split(",")) - {""}
        best: dict[int, float] = {}
        for row in self.db.execute(
            "SELECT room_id, scenery, seen FROM fingerprint WHERE exits = ?", (ex,)
        ):
            have = set(row["scenery"].split(",")) - {""}
            union = want | have
            # Two rooms that both report no scenery are not thereby the same
            # room -- that is absence of evidence, and scoring it as a perfect
            # match let every bare corridor with the same exits stand in for
            # every other.  Identifying a room needs something positive.
            score = len(want & have) / len(union) if union else 0.0
            if score > best.get(row["room_id"], -1.0):
                best[row["room_id"]] = score
        return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))

    def by_name(self, name: str, exits: Iterable[str] | None = None) -> list[int]:
        """Rooms with this name, narrowed by exits when we have them.

        The way into an imported map: MIP names the room you are in, and a
        third of 3K's rooms are unique on name and exits together.  The rest
        -- the thousand-odd rooms called "A battleground" -- come back as a
        list for walking to narrow.
        """
        rows = self.db.execute(
            "SELECT id FROM room WHERE LOWER(name) = ?", (name.strip().lower(),)
        ).fetchall()
        ids = [int(r["id"]) for r in rows]
        if exits is None:
            return ids
        want = self.fingerprint(exits, ())[0]
        return [r for r in ids
                if any(f["exits"] == want for f in self.db.execute(
                    "SELECT exits FROM fingerprint WHERE room_id = ?", (r,)))]

    def landmark(self, name: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM landmark WHERE LOWER(name) = ?",
            (name.strip().lower(),)).fetchone()

    def landmarks(self, text: str = "", limit: int = 20) -> list[sqlite3.Row]:
        like = f"%{text.strip().lower()}%"
        return list(self.db.execute(
            "SELECT * FROM landmark WHERE LOWER(name) LIKE ? OR LOWER(note) "
            "LIKE ? ORDER BY LENGTH(name), name LIMIT ?", (like, like, limit)))

    def consistent(self, room_id: int, exits: Iterable[str],
                   scenery: Iterable[str]) -> bool:
        """Could this be that room?

        Weaker than :meth:`candidates`, and deliberately so.  Identifying a
        room out of nowhere needs positive evidence; checking that the room
        dead reckoning predicted is not contradicted only needs the exits to
        agree and the scenery not to disagree.  A room that reports no scenery
        contradicts nothing.
        """
        ex, sc = self.fingerprint(exits, scenery)
        want = set(sc.split(",")) - {""}
        for row in self.db.execute(
            "SELECT scenery FROM fingerprint WHERE room_id = ? AND exits = ?",
            (room_id, ex),
        ):
            have = set(row["scenery"].split(",")) - {""}
            if not want or not have or (want & have):
                return True

        # An imported room's exits are only as good as what was recorded, and
        # a room can hold more ways out than it lists: the Chapel's map entry
        # knows about its stairs and its trapdoor, while DDD reports only the
        # door west.  So also accept when every exit MIP names is one the map
        # already has for that room.  Weaker than equality, and deliberately:
        # this checks a room dead reckoning already predicted.  Identifying a
        # room out of nowhere still goes through candidates(), which does not
        # accept this.
        mine = {e.strip().lower() for e in exits if e.strip()}
        if not mine:
            return False
        known = {str(e["command"]).lower() for e in self.exits_from(room_id)}
        return mine <= known

    # --- edges --------------------------------------------------------------

    def link(self, from_room: int, command: str, to_room: int,
             at: float | None = None) -> None:
        now = time.time() if at is None else at
        self.db.execute(
            "INSERT INTO edge (from_room, command, to_room, seen, last_seen) "
            "VALUES (?,?,?,1,?) "
            "ON CONFLICT(from_room, command, to_room) DO UPDATE SET "
            "seen = seen + 1, last_seen = excluded.last_seen",
            (from_room, command.strip().lower(), to_room, now),
        )

    def mark_failed(self, from_room: int, command: str) -> None:
        """This way out did not work.  Remember, so routing stops choosing it."""
        self.db.execute(
            "UPDATE edge SET failed = failed + 1 WHERE from_room = ? "
            "AND command = ?", (from_room, command.strip().lower()))

    def mark_worked(self, from_room: int, command: str) -> None:
        """It worked after all -- a locked door opened, a spell came back."""
        self.db.execute(
            "UPDATE edge SET failed = 0 WHERE from_room = ? AND command = ?",
            (from_room, command.strip().lower()))

    def exits_from(self, room_id: int) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT * FROM edge WHERE from_room = ? ORDER BY seen DESC", (room_id,)
        ))

    def neighbours(self, room_id: int) -> set[int]:
        """Rooms adjacent either way.

        Edges are directed -- walking east does not promise a way back -- but
        for *drawing*, a room you arrived from is still next door.  Routing
        keeps following the arrows.
        """
        rows = self.db.execute(
            "SELECT to_room AS r FROM edge WHERE from_room = ? "
            "UNION SELECT from_room AS r FROM edge WHERE to_room = ?",
            (room_id, room_id),
        )
        return {int(row["r"]) for row in rows}

    def destination(self, room_id: int, command: str) -> int | None:
        """Where this command usually goes.  Usually, not always -- a random
        exit keeps every destination it has ever had."""
        row = self.db.execute(
            "SELECT to_room FROM edge WHERE from_room = ? AND command = ? "
            "ORDER BY seen DESC LIMIT 1", (room_id, command.strip().lower())
        ).fetchone()
        return None if row is None else int(row["to_room"])

    # --- regions ------------------------------------------------------------

    def add_region(self, name: str, parent_id: int | None = None,
                   layout: str = "grid") -> int:
        cur = self.db.execute(
            "INSERT INTO region (name, parent_id, layout) VALUES (?,?,?)",
            (name, parent_id, layout),
        )
        return int(cur.lastrowid)

    def assign(self, room_ids: Iterable[int], region_id: int | None) -> None:
        self.db.executemany(
            "UPDATE room SET region_id = ? WHERE id = ?",
            [(region_id, r) for r in room_ids],
        )

    def region_by_name(self, name: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM region WHERE LOWER(name) = ?", (name.strip().lower(),)
        ).fetchone()

    def reparent(self, region_id: int, parent_id: int | None) -> str | None:
        """Nest one region inside another.  Refuses to make a loop: containment
        is a tree, and a cycle would make "which area is this" unanswerable."""
        walk, seen = parent_id, set()
        while walk is not None and walk not in seen:
            if walk == region_id:
                return "that would put a region inside itself"
            seen.add(walk)
            row = self.db.execute(
                "SELECT parent_id FROM region WHERE id = ?", (walk,)
            ).fetchone()
            walk = None if row is None else row["parent_id"]
        self.db.execute("UPDATE region SET parent_id = ? WHERE id = ?",
                        (parent_id, region_id))
        return None

    def region_tree(self) -> list[tuple[int, sqlite3.Row, int]]:
        """(depth, region, room count), outermost first, for printing."""
        kids: dict[int | None, list] = {}
        for row in self.db.execute("SELECT * FROM region ORDER BY name"):
            kids.setdefault(row["parent_id"], []).append(row)
        counts = {r["region_id"]: r["n"] for r in self.db.execute(
            "SELECT region_id, COUNT(*) n FROM room WHERE region_id IS NOT NULL "
            "GROUP BY region_id")}
        out: list[tuple[int, sqlite3.Row, int]] = []

        def walk(parent, depth):
            for row in kids.get(parent, []):
                out.append((depth, row, counts.get(row["id"], 0)))
                walk(row["id"], depth + 1)

        walk(None, 0)
        return out

    def region_path(self, room_id: int) -> list[str]:
        """['Chaos', 'Tree of Life'] -- outermost first."""
        row = self.db.execute(
            "SELECT region_id FROM room WHERE id = ?", (room_id,)
        ).fetchone()
        names, seen = [], set()
        rid = None if row is None else row["region_id"]
        while rid is not None and rid not in seen:
            seen.add(rid)                      # a cycle would hang the UI
            r = self.db.execute(
                "SELECT name, parent_id FROM region WHERE id = ?", (rid,)
            ).fetchone()
            if r is None:
                break
            names.append(r["name"])
            rid = r["parent_id"]
        return list(reversed(names))

    # --- the log ------------------------------------------------------------

    def log(self, session_id: int | None, kind: str, text: str,
            at: float | None = None, room_id: int | None = None,
            channel: str | None = None, who: str | None = None) -> int:
        now = time.time() if at is None else at
        cur = self.db.execute(
            "INSERT INTO line (session_id, at, kind, room_id, channel, who, text) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, now, kind, room_id, channel, who, text),
        )
        rid = int(cur.lastrowid)
        self.db.execute(
            "INSERT INTO line_fts (rowid, text) VALUES (?,?)", (rid, text)
        )
        return rid

    def search(self, query: str, limit: int = 100, kind: str | None = None,
               room_id: int | None = None) -> list[sqlite3.Row]:
        """Full-text search, newest first.

        The query goes to FTS5, whose syntax is its own little language -- an
        unbalanced quote or a bare NEAR is a hard error, and a search box
        should not throw.  Malformed queries fall back to a phrase match.
        """
        where, args = ["line_fts MATCH ?"], [query]
        if kind is not None:
            where.append("line.kind = ?")
            args.append(kind)
        if room_id is not None:
            where.append("line.room_id = ?")
            args.append(room_id)
        sql = (
            "SELECT line.* FROM line_fts JOIN line ON line.id = line_fts.rowid "
            f"WHERE {' AND '.join(where)} ORDER BY line.at DESC LIMIT ?"
        )
        try:
            return list(self.db.execute(sql, (*args, limit)))
        except sqlite3.OperationalError:
            args[0] = '"' + query.replace('"', '""') + '"'
            return list(self.db.execute(sql, (*args, limit)))

    def context(self, line_id: int, before: int = 5,
                after: int = 5) -> list[sqlite3.Row]:
        """The lines around a hit -- a search result on its own rarely says
        enough, and this is what makes the log readable rather than a grep."""
        row = self.db.execute(
            "SELECT session_id, at FROM line WHERE id = ?", (line_id,)
        ).fetchone()
        if row is None:
            return []
        earlier = list(self.db.execute(
            "SELECT * FROM line WHERE session_id IS ? AND id <= ? "
            "ORDER BY id DESC LIMIT ?", (row["session_id"], line_id, before + 1)
        ))
        later = list(self.db.execute(
            "SELECT * FROM line WHERE session_id IS ? AND id > ? "
            "ORDER BY id LIMIT ?", (row["session_id"], line_id, after)
        ))
        return list(reversed(earlier)) + later

    def tail(self, session_id: int | None, limit: int = 400) -> list[sqlite3.Row]:
        """The last few lines of a session, oldest first.

        What the terminal puts back after a refresh.  Taken from the log rather
        than kept in memory because the log is where it already is, and because
        it then survives the client being restarted as well.
        """
        if session_id is None:
            return []
        rows = self.db.execute(
            "SELECT * FROM line WHERE session_id = ? AND kind IN ('recv','sent') "
            "ORDER BY id DESC LIMIT ?", (session_id, max(0, limit))).fetchall()
        return rows[::-1]

    def lines(self, session_id: int) -> Iterator[sqlite3.Row]:
        yield from self.db.execute(
            "SELECT * FROM line WHERE session_id = ? ORDER BY id", (session_id,)
        )
