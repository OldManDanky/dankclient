"""Replay a capture through the mapper and report what it built."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.capture import replay
from mud.mapper import Mapper
from mud.scanner import Scanner
from mud.state import World
from mud.store import Store


def walk(stem, store=None):
    store = store or Store()
    mapper = Mapper(store)
    scan, world = Scanner(), World()
    last, opened = None, None

    def settle():
        # The block is complete, but the time that matters is when it *opened*.
        # Settling waits for the next non-H** message, which can be a couple of
        # seconds away on the tick -- long enough to push the command that
        # caused the move outside the attribution window.
        mapper.arrived(list(world.room.exits),
                       [o.name for o in world.room.scenery], at=opened)

    for kind, ts, payload in replay(stem):
        if kind == "sent":
            mapper.sent(payload, ts)
            continue
        for ev in scan.feed(payload):
            code = getattr(ev, "code", None)
            if code is None:
                continue
            # The room block is DDD plus the H** run that follows it.
            if opened is not None and code not in ("HAA", "HAB"):
                settle()
                opened = None
            if code == "DDD" and last != "BAD":
                opened = ts
            world.apply(code, ev.data)
            last = code
    if opened is not None:
        settle()
    return store, mapper


if __name__ == "__main__":
    store, mapper = walk(sys.argv[1])
    rooms = store.db.execute("SELECT COUNT(*) c FROM room").fetchone()["c"]
    edges = store.db.execute("SELECT COUNT(*) c FROM edge").fetchone()["c"]
    visits = store.db.execute("SELECT SUM(visits) s FROM room").fetchone()["s"]
    print(f"rooms={rooms}  edges={edges}  arrivals={visits}  here={mapper.here}")
    print("\nmost-visited:")
    for r in store.db.execute(
        "SELECT r.id, r.visits, f.exits FROM room r JOIN fingerprint f "
        "ON f.room_id = r.id ORDER BY r.visits DESC, r.id LIMIT 8"
    ):
        print(f"  room {r['id']:3}  visits {r['visits']:2}  {r['exits']}")
