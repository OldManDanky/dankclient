#!/usr/bin/env python3
"""Bring an imported map up to date and take out what the client invented.

Run with the client stopped.  Three things, all of which the importer now
does on its own -- this is for a map imported before it did:

  * give rooms their exits from their edges where tt++ left the title bare
  * remove rooms added after the import, which are duplicates of rooms the
    map already had and which nothing will ever join up
  * lock it, so it stops happening
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.store import Store  # noqa: E402


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "map.sqlite"
    store = Store(path)

    highest = store.db.execute(
        "SELECT MAX(room_id) m FROM landmark").fetchone()["m"] or 0
    # Everything the import created is below the last vnum it saw; anything
    # above came later.  Ask rather than assume where that line falls.
    imported = store.db.execute(
        "SELECT MAX(id) m FROM room WHERE visits = 0").fetchone()["m"] or 0
    cutoff = max(highest, imported)

    filled = store.backfill_exits()
    cleaned = store.clean_exits()
    strays = [int(r["id"]) for r in store.db.execute(
        "SELECT id FROM room WHERE id > ?", (cutoff,))]
    for room in strays:
        store.forget(room)
    store.locked = True

    print(f"{filled} rooms took their exits from their edges")
    print(f"{cleaned} rooms had a macro taken back out of their exits")
    print(f"{len(strays)} rooms added after the import were removed"
          + (f": {strays}" if strays else ""))
    print(f"the map is locked; {store.db.execute('SELECT COUNT(*) c FROM room')
                                .fetchone()['c']} rooms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
