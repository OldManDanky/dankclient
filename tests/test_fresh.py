"""Updates -> Fresh copy: drop this client's copy of 3kdb's data, take theirs.

An ordinary update only ever adds, which is right for an update and cannot
fix anything that is already wrong -- an importer corrected since, or rooms an
older client invented while the map could still grow.  This is the way out of
that, and the thing it must not cost is the session log: 28,824 lines in the
dev map are filed by room, and deleting a room sets its lines' room to NULL on
the way out.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import update  # noqa: E402
from mud.store import Store  # noqa: E402
from mud.tintin import import_map  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_tintin import SAMPLE, SPEEDRUNS  # noqa: E402


def unpacked() -> Path:
    """3kdb, as `pull` would have left it after unpacking the tarball."""
    root = Path(tempfile.mkdtemp())
    (root / "common" / "map").mkdir(parents=True)
    (root / update.WANTED["map"]).write_text(SAMPLE)
    (root / update.WANTED["speedruns"]).write_text(SPEEDRUNS)
    return root


class instead_of_the_network:
    """3kdb's tarball, without 3kdb and without the network.

    `_unpack` writes into the directory it is handed and its return value is
    not used, so a stub has to copy rather than point: the first draft of
    these tests pointed, `pull` looked in its own empty temp directory, and
    every import quietly did nothing.  Before that it went to the network for
    real and pulled the true 25MB map -- which has a real room 64, so a room
    this client had invented appeared to survive being dropped.
    """

    def __init__(self, root: Path, tree: bytes = b""):
        self.root, self.tree = root, tree

    def __enter__(self):
        self.was = (update._get, update._unpack)
        update._get = lambda url, timeout: self.tree
        update._unpack = lambda blob, into: (
            shutil.copytree(self.root, into, dirs_exist_ok=True), into)[1]
        return self

    def __exit__(self, *exc):
        update._get, update._unpack = self.was
        return False


def tree_of(*keys) -> bytes:
    """What GitHub says it has, for the keys named."""
    return json.dumps({"tree": [
        {"path": update.WANTED[k], "sha": f"sha-{k}", "size": 10, "type": "blob"}
        for k in keys]}).encode()


def took(store, routes, want, fresh=False, root=None) -> dict:
    root = root if root is not None else unpacked()
    with instead_of_the_network(root):
        return update.pull(store, routes, want=want, fresh=fresh)


def played_on() -> tuple:
    """A map taken once and then played on: a room renamed, an exit walked,
    a room the client invented, and a log filed by room."""
    store = Store()
    root = unpacked()
    import_map(store, root / update.WANTED["map"])
    store.db.execute("UPDATE room SET name = 'My own name', visits = 40 "
                     "WHERE id = 1")
    store.locked = False
    mine = store.add_room("A room 3kdb has never heard of")
    store.locked = True
    store.link(1, "secret", mine)
    session = store.begin_session()
    for kind, room in (("recv", 1), ("recv", 2), ("recv", mine)):
        store.db.execute(
            "INSERT INTO line (session_id, at, kind, room_id, text) "
            "VALUES (?,?,?,?,?)", (session, 1.0, kind, room, "a line"))
    return store, root, mine


def filed(store) -> dict:
    return {int(r["room_id"]): int(r["c"]) for r in store.db.execute(
        "SELECT room_id, COUNT(*) c FROM line WHERE room_id IS NOT NULL "
        "GROUP BY room_id")}


def test_a_fresh_copy_puts_back_what_the_client_had_changed():
    store, root, _mine = played_on()
    assert store.room(1)["name"] == "My own name"

    got = took(store, None, ["map"], fresh=True, root=root)

    assert not got["error"], got
    assert store.room(1)["name"] == "The Center of Town", "3kdb's name again"
    assert store.room(1)["visits"] == 0, "and its own visit count"


def test_a_fresh_copy_takes_away_a_room_the_client_invented():
    store, root, mine = played_on()
    assert store.room(mine) is not None

    took(store, None, ["map"], fresh=True, root=root)

    assert store.room(mine) is None, "not 3kdb's, so not in the fresh copy"
    assert store.destination(1, "secret") is None


def test_a_fresh_copy_keeps_the_session_log_filed_by_room():
    """The room ids are 3kdb's own room numbers, so a line filed under room 1
    belongs under room 1 again the moment the map is back."""
    store, root, mine = played_on()
    assert filed(store) == {1: 1, 2: 1, mine: 1}

    got = took(store, None, ["map"], fresh=True, root=root)

    assert filed(store) == {1: 1, 2: 1}, "the two 3kdb rooms keep their lines"
    assert got["did"]["map"]["refiled"] == 2
    assert got["did"]["map"]["unfiled"] == 1, "the invented room's line"
    assert store.db.execute("SELECT COUNT(*) c FROM line").fetchone()["c"] == 3, \
        "and no line was thrown away"


def test_an_ordinary_update_still_only_adds():
    store, root, mine = played_on()

    took(store, None, ["map"], root=root)

    assert store.room(1)["name"] == "My own name", "a merge leaves names alone"
    assert store.room(1)["visits"] == 40
    assert store.room(mine) is not None, "and keeps what it does not know about"
    assert filed(store) == {1: 1, 2: 1, mine: 1}


def test_a_fresh_copy_of_the_destinations_drops_the_old_names():
    store, root, _mine = played_on()
    took(store, None, ["speedruns"], root=root)
    store.db.execute("INSERT OR REPLACE INTO landmark (name, room_id, kind, note) "
                     "VALUES ('gone-from-3kdb', 1, 'misc', 'stale')")

    took(store, None, ["speedruns"], fresh=True, root=root)

    assert store.landmark("cot") is not None, "3kdb's are back"
    assert store.landmark("gone-from-3kdb") is None, "and only 3kdb's"


def routestore():
    from mud.botstore import RouteStore

    class Bare:
        bots = None

    return RouteStore(Bare(), Path(tempfile.mkdtemp()) / "routes.json")


def with_bots(root: Path) -> Path:
    """3kdb's bot library: a listing, and one file per route."""
    where = root / "common" / "bot"
    (where / "bots").mkdir(parents=True, exist_ok=True)
    (where / "bots.tin").write_text(
        ".add_bot {ratrun} {ratrun} {Rats} {1} {0} {1} {};\n"
        ".add_bot {curs} {curs} {Curs} {2} {0} {1} {};\n")
    for name, path in (("ratrun", "n;e;s"), ("curs", "w;w")):
        (where / "bots" / f"{name}.tin").write_text(
            "#alias .add_bot {\n"
            f"  #var bot[path] {{{path}}};\n"
            "};\n")
    return root


def test_a_fresh_copy_replaces_3kdbs_routes_and_keeps_your_own():
    """A route of 3kdb's that you have edited is theirs again -- that is what
    was asked for.  A route that is only yours is not in their listing, so
    nothing here can touch it."""
    store, root, _mine = played_on()
    with_bots(root)
    routes = routestore()
    took(store, routes, ["bots"], root=root)
    assert {r.name for r in routes.routes} == {"ratrun", "curs"}

    ratrun = next(r for r in routes.routes if r.name == "ratrun")
    routes.upsert({"id": ratrun.id, "name": "ratrun", "path": "u;u;u"})
    routes.upsert({"name": "my own run", "path": "d;d"})

    got = took(store, routes, ["bots"], fresh=True, root=root)

    by_name = {r.name: r for r in routes.routes}
    assert by_name["ratrun"].path == "n;e;s", "3kdb's path, not the edit"
    assert by_name["my own run"].path == "d;d", "and mine is left alone"
    assert got["did"]["bots"]["dropped"] == 2


def test_an_ordinary_update_leaves_an_edited_route_alone():
    store, root, _mine = played_on()
    with_bots(root)
    routes = routestore()
    took(store, routes, ["bots"], root=root)
    ratrun = next(r for r in routes.routes if r.name == "ratrun")
    routes.upsert({"id": ratrun.id, "name": "ratrun", "path": "u;u;u"})

    got = took(store, routes, ["bots"], root=root)

    assert next(r for r in routes.routes if r.name == "ratrun").path == "u;u;u"
    assert got["did"]["bots"]["dropped"] == 0


def test_a_fresh_copy_is_taken_even_when_nothing_has_changed():
    """That is the whole point of it: the sha is the same, and the copy here
    is the one that is wrong."""
    store, root, _mine = played_on()
    every = tree_of(*update.WANTED)
    with instead_of_the_network(root, every):
        assert update.sync(store, None, want=["map"])["did"].get("map"), \
            "an ordinary take merges"
        assert update.check(store)["changed"] == ["speedruns", "bots", "gags"], \
            "and the map is up to date afterwards"

        store.db.execute("UPDATE room SET name = 'Wrong' WHERE id = 1")
        got = update.sync(store, None, want=["map"], fresh=True)

    assert not got.get("nothing"), got
    assert store.room(1)["name"] == "The Center of Town", "3kdb's, not ours"


def test_a_fresh_copy_of_something_the_repository_lost_drops_nothing():
    """Dropping what we have and putting nothing back is the one outcome
    worth refusing outright."""
    store, root, _mine = played_on()
    with instead_of_the_network(root, tree_of()):
        got = update.sync(store, None, want=["map"], fresh=True)

    assert got.get("nothing") is True, got
    assert store.room(1) is not None, "the map we had is still here"


# --- saying it worked --------------------------------------------------------

def test_the_summary_says_what_was_taken():
    said = update.summary({"did": {
        "map": {"rooms": 51720, "edges": 71394, "refiled": 28672, "unfiled": 152},
        "speedruns": {"added": 1247},
        "bots": {"added": 145, "kept": 3},
        "gags": {"gags": 88}}}, fresh=True)
    assert said.startswith("fresh copy finished: ")
    for want in ("51,720 rooms", "71,394 exits", "152 of your logged lines",
                 "1,247 destinations", "145 routes", "3 of yours left alone",
                 "88 gags"):
        assert want in said, (want, said)


def test_the_summary_says_so_when_there_was_nothing_to_take():
    assert update.summary({"nothing": True}) == "already up to date -- nothing to take."


def test_the_summary_says_so_when_it_failed():
    """The worst version of the missing line: progress, then silence."""
    assert update.summary({"error": "URLError: timed out"}) == \
        "update failed: URLError: timed out"
    assert update.summary({"did": {}}) == "update finished, but it took nothing."


def test_the_screen_is_told_when_an_update_finishes():
    """Driving the real web op: the panel always knew, the screen never did."""
    import asyncio
    from mud.session import Session
    from mud.web import WebServer

    store, root, _mine = played_on()
    session = Session(jumpstart=False, sec_code=1, store=store)
    web = WebServer(session)
    out: list[str] = []
    web.push = lambda msg: out.append(msg.get("d", "")) if msg.get("t") == "text" else None
    # The whole op, not just the pull: `sync` asks GitHub what it has before
    # taking anything, and that goes down the same `_get`.
    with instead_of_the_network(root, tree_of("map")):
        asyncio.new_event_loop().run_until_complete(
            web._update_op({"op": "pull", "want": ["map"], "fresh": True}))
    screen = "".join(out)
    assert "fresh copy finished:" in screen, screen
    assert "rooms" in screen and "exits" in screen, screen
