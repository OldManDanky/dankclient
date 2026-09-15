"""Rules and paths can be reordered: dragged in Options, or moved from a grip.

Order is not cosmetic for triggers.  Of equal priority they are tried in the
order the list has them, and a stop rule ends the rest there -- so the list's
order has to be the firing order, which it was not until triggers remembered
when they were added.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.botstore import RouteStore  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.triggers import Trigger, TriggerSet  # noqa: E402
from mud.web import WebServer  # noqa: E402


class Bench:
    def __init__(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.session = Session("127.0.0.1", 1, sec_code=1)
        self.host = ScriptHost(self.session, self.folder)
        self.rules = RuleStore(self.host, self.folder / "rules.json")
        self.host.rules = self.rules
        self.routes = RouteStore(self.host, self.folder / "routes.json")
        self.host.routes = self.routes

    def rule(self, name: str, group: str = "", pattern: str = "", stop: bool = False):
        rule, err = self.rules.upsert({
            "kind": "trigger", "name": name, "group": group, "pattern": pattern or name,
            "mode": "contains", "stop": stop, "actions": [{"type": "send", "text": name}]})
        assert err is None, err
        return rule

    def names(self) -> list[str]:
        return [r.name for r in self.rules.rules]

    def close(self) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)


def test_equal_priority_triggers_are_tried_in_the_order_they_were_added():
    """Not in the order of the buckets they are filed in for speed."""
    ts = TriggerSet()
    first = ts.add(Trigger("rat arrives", lambda m: None, "contains"))
    second = ts.add(Trigger(r".*", lambda m: None, "regex"))     # no literal: always tried
    assert [t for t, _ in ts.fire("A rat arrives.")] == [first, second]
    high = ts.add(Trigger("rat", lambda m: None, "contains", priority=-5))
    assert [t for t, _ in ts.fire("A rat arrives.")][0] is high, "priority still comes first"


def test_a_rule_moves_before_another_and_the_order_is_kept():
    b = Bench()
    try:
        aa, bb, cc = b.rule("aa"), b.rule("bb"), b.rule("cc")
        assert b.rules.move(cc.id, aa.id)
        assert b.names() == ["cc", "aa", "bb"]
        saved = json.loads((b.folder / "rules.json").read_text())
        assert [r["name"] for r in saved] == ["cc", "aa", "bb"]
        assert b.rules.move(cc.id, "")                  # last in its folder
        assert b.names() == ["aa", "bb", "cc"]
        assert not b.rules.move("nobody", aa.id)
        assert not b.rules.move(aa.id, aa.id)
        assert not b.rules.move(aa.id, "nobody")
        assert b.names() == ["aa", "bb", "cc"], "a move that cannot happen changes nothing"
    finally:
        b.close()


def test_dropped_among_another_folders_rules_it_is_filed_there():
    b = Bench()
    try:
        b.rule("aa", "party")
        b.rule("bb", "party")
        cc = b.rule("cc")
        b.rule("dd")
        assert b.rules.move(cc.id, "", "party")
        assert b.names() == ["aa", "bb", "cc", "dd"]
        assert b.rules.rules[2].group == "party"
    finally:
        b.close()


def test_moving_a_trigger_up_the_list_makes_it_the_one_that_fires():
    b = Bench()
    try:
        first = b.rule("first", pattern="rat arrives", stop=True)
        second = b.rule("second", pattern="rat", stop=True)
        fired = lambda: [t.fn.__name__ for t, _ in b.host.triggers.fire("A rat arrives.")]
        assert fired() == ["first"]
        assert b.rules.move(second.id, first.id)
        assert fired() == ["second"], "the stop rule now at the top ends the rest"
    finally:
        b.close()


def test_paths_move_too():
    b = Bench()
    try:
        ra, _ = b.routes.upsert({"name": "ra", "path": "n"})
        rb, _ = b.routes.upsert({"name": "rb", "path": "s"})
        rc, _ = b.routes.upsert({"name": "rc", "path": "e", "group": "far"})
        assert b.routes.move(rc.id, ra.id, "")
        assert [r.name for r in b.routes.routes] == ["rc", "ra", "rb"]
        assert b.routes.routes[0].group == ""
        saved = json.loads((b.folder / "routes.json").read_text())
        assert [r["name"] for r in saved] == ["rc", "ra", "rb"]
    finally:
        b.close()


def test_the_page_moves_rules_and_paths():
    b = Bench()
    try:
        aa, bb = b.rule("aa"), b.rule("bb")
        b.routes.upsert({"name": "ra", "path": "n"})
        rb, _ = b.routes.upsert({"name": "rb", "path": "s"})
        web = WebServer(b.session, scripts=b.host)
        pushed: list[dict] = []
        web.push = pushed.append
        web._on_client_message(json.dumps(
            {"t": "rules", "op": "move", "id": bb.id, "before": aa.id, "group": ""}).encode())
        web._on_client_message(json.dumps(
            {"t": "routes", "op": "move", "id": rb.id, "before": "", "group": "far"}).encode())
        assert b.names() == ["bb", "aa"]
        assert [r.name for r in b.routes.routes] == ["ra", "rb"]
        assert b.routes.routes[1].group == "far"
        assert {m["t"] for m in pushed} >= {"rules", "routes"}, "both lists come back redrawn"
    finally:
        b.close()
