"""Folders: the routes and rules lists, once they are too long to read.

67 routes now and 141 after a full 3kdb import, against four rules -- so the
crowding is the routes list, and it had no grouping at all while rules had
had one flat level since 0.2.14.  Both use one field and one meaning now: a
`/`-separated path, which the CMUD importer has been writing into a rule's
group since 0.2.16 ("areas/zombies").

A folder is not a thing.  It is the prefix its items carry, so there is
nothing to create and nothing empty to tidy up, and renaming one is a rewrite
of that prefix wherever it starts one -- which is why the folders beneath it
come along.  Nothing here can lose an item: an empty new name files them at
the top instead of deleting them.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.botstore import MOST_DEPTH, Route, RouteStore, folder  # noqa: E402
from mud.rules import Rule, RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402


class Bare:
    bots = None


def routes(*pairs) -> RouteStore:
    store = RouteStore(Bare(), Path(tempfile.mkdtemp()) / "r.json")
    for name, group in pairs:
        store.upsert({"name": name, "path": "n", "group": group})
    return store


def rules(*pairs) -> RuleStore:
    """A real ScriptHost: `register()` needs somewhere to hang the triggers,
    and a store with a stand-in host passes these tests by never getting that
    far."""
    where = Path(tempfile.mkdtemp())
    session = Session("127.0.0.1", 1, sec_code=12345)
    session._writer = object()
    host = ScriptHost(session, where)
    store = RuleStore(host, where / "rules.json")
    host.rules = store
    store.rules = [Rule(kind="alias", pattern=name, group=group,
                        actions=[{"type": "send", "text": "x"}])
                   for name, group in pairs]
    store.register()
    return store


# --- the path ----------------------------------------------------------------

def test_a_folder_path_is_tidied_but_keeps_its_capitals():
    """A label is the player's business; only the whitespace is ours."""
    assert folder("  Chaos // Dungeon / ") == "Chaos/Dungeon"
    assert folder("") == "" and folder(None) == ""


def test_it_cannot_nest_for_ever():
    assert folder("/".join("abcdefgh")) == "/".join("abcdefgh"[:MOST_DEPTH])


def test_a_rule_and_a_route_tidy_it_the_same_way():
    assert (Route(name="x", path="n", group=" a / b ").group
            == Rule(kind="alias", pattern="x", group=" a / b ").group == "a/b")


# --- what folders there are --------------------------------------------------

def test_every_prefix_is_a_folder():
    """"chaos/dungeon" makes "chaos" exist, with nothing filed in it."""
    assert routes(("a", "chaos/dungeon")).folders() == ["chaos", "chaos/dungeon"]


def test_a_folder_exists_only_while_something_is_in_it():
    store = routes(("a", "chaos"))
    store.delete(store.routes[0].id)
    assert store.folders() == []


# --- moving and renaming -----------------------------------------------------

def test_filing_a_route_moves_it():
    store = routes(("a", ""))
    store.file_in(store.routes[0].id, " chaos / dungeon ")
    assert store.routes[0].group == "chaos/dungeon"


def test_renaming_a_folder_brings_the_ones_under_it_along():
    store = routes(("a", "chaos"), ("b", "chaos/dungeon"),
                   ("c", "chaos/dungeon/deep"), ("d", "elsewhere"))
    assert store.rename_folder("chaos", "Chaos Realm") == 3
    assert [r.group for r in store.routes] == [
        "Chaos Realm", "Chaos Realm/dungeon", "Chaos Realm/dungeon/deep",
        "elsewhere"]


def test_renaming_to_nothing_files_them_at_the_top_and_keeps_them():
    store = routes(("a", "chaos"), ("b", "chaos/dungeon"))
    assert store.rename_folder("chaos", "") == 2
    assert [r.group for r in store.routes] == ["", "dungeon"]
    assert len(store.routes) == 2, "a rename must never lose a route"


def test_renaming_nothing_is_refused_rather_than_moving_everything():
    store = routes(("a", ""), ("b", "chaos"))
    assert store.rename_folder("", "x") == 0
    assert [r.group for r in store.routes] == ["", "chaos"]


def test_a_rules_group_renames_the_same_way():
    store = rules(("a", "areas"), ("b", "areas/zombies"), ("c", "party"))
    assert store.rename_group("areas", "Areas") == 2
    assert [r.group for r in store.rules] == ["Areas", "Areas/zombies", "party"]


# --- switching ---------------------------------------------------------------

def test_switching_a_group_off_reaches_the_folders_under_it():
    """Otherwise a folded-away folder keeps firing while its parent shows off."""
    store = rules(("a", "areas"), ("b", "areas/zombies"), ("c", "elsewhere"))
    store.set_group("areas", False)
    assert [r.enabled for r in store.rules] == [False, False, True]


def test_switching_a_group_is_not_fooled_by_a_name_that_starts_the_same():
    store = rules(("a", "areas"), ("b", "areasfoo"))
    store.set_group("areas", False)
    assert [r.enabled for r in store.rules] == [False, True]


def test_switching_no_group_switches_nothing():
    store = rules(("a", ""), ("b", "areas"))
    store.set_group("", False)
    assert [r.enabled for r in store.rules] == [True, True]


# --- one folder across both stores -------------------------------------------

def both(*items) -> tuple:
    """A ScriptHost with rules and routes, which is where a folder is one name.

    ("trigger", "zodiacs") is a rule; ("route", "zodiacs") is a route.
    """
    from mud.scripts import ScriptHost
    from mud.session import Session
    where = Path(tempfile.mkdtemp())
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    session._writer = object()
    host = ScriptHost(session, where)
    host.rules = RuleStore(host, where / "rules.json")
    host.routes = RouteStore(host, where / "routes.json")
    host.rules.rules = [
        Rule(kind=kind, pattern=f"p{n}", name=f"n{n}", every=290, group=group,
             actions=[{"type": "send", "text": "x"}])
        for n, (kind, group) in enumerate(items) if kind != "route"]
    host.rules.register()
    for n, (kind, group) in enumerate(items):
        if kind == "route":
            host.routes.upsert({"name": f"r{n}", "path": "n;s", "group": group})
    return session, host


def test_a_folder_counts_every_kind_and_the_routes_with_them():
    _s, host = both(("trigger", "zodiacs"), ("alias", "zodiacs"),
                    ("timer", "zodiacs/hunting"), ("route", "zodiacs"),
                    ("trigger", "markets"))
    by = {row["path"]: row for row in host.folders()}
    assert set(by) == {"zodiacs", "zodiacs/hunting", "markets"}
    assert by["zodiacs"]["kinds"] == {"trigger": 1, "alias": 1, "timer": 1,
                                      "route": 1}, by["zodiacs"]["kinds"]
    assert by["zodiacs"]["count"] == 4 and by["zodiacs"]["here"] == 3
    assert by["zodiacs/hunting"]["count"] == 1


def test_switching_a_folder_reaches_the_rules_and_the_routes():
    """The seam this was built to close: `/group zodiacs off` used to leave
    the area's route walking, because routes are a store of their own."""
    _s, host = both(("trigger", "zodiacs"), ("route", "zodiacs"),
                    ("timer", "zodiacs/hunting"), ("trigger", "markets"))
    assert host.set_folder("zodiacs", False) == {"rules": 2, "routes": 1}
    assert [r.enabled for r in host.rules.rules] == [False, False, True]
    assert host.routes.routes[0].enabled is False


def test_a_route_switched_off_refuses_to_walk():
    """Refused in the store, not the panel: a folder that is off has to mean
    the route does not walk however it was asked for."""
    import asyncio
    # Starting one for real needs a loop to put the bot's task on; without
    # this the second half passes only when some earlier test left one behind.
    asyncio.set_event_loop(asyncio.new_event_loop())
    _s, host = both(("route", "zodiacs"))
    route = host.routes.routes[0]
    host.set_folder("zodiacs", False)
    assert host.routes.start(route.id) == "r0 is switched off"
    host.set_folder("zodiacs", True)
    assert host.routes.start(route.id) != "r0 is switched off"


def test_renaming_a_folder_renames_it_in_both_stores():
    _s, host = both(("trigger", "zodiacs"), ("route", "zodiacs"))
    assert host.rename_folder("zodiacs", "Zodiacs") == {"rules": 1, "routes": 1}
    assert host.rules.rules[0].group == "Zodiacs"
    assert host.routes.routes[0].group == "Zodiacs"


def test_the_folders_command_lists_both_kinds():
    from mud import commands
    session, host = both(("trigger", "zodiacs"), ("route", "zodiacs"))
    said = []
    commands.handle("/folders", session, host, said.append)
    out = "\n".join(said)
    assert "zodiacs" in out and "1 trigger" in out and "1 route" in out, out


def test_the_group_command_says_it_switched_the_routes_too():
    from mud import commands
    session, host = both(("trigger", "zodiacs"), ("route", "zodiacs"))
    said = []
    commands.handle("/group zodiacs off", session, host, said.append)
    assert "1 route(s)" in "\n".join(said), said
    assert host.routes.routes[0].enabled is False
