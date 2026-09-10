"""Where you can go by name: /speedruns, Options -> Marks, and the one search
that tells both how far each place is.

The speedruns imported from 3kdb are the names /go knows -- 399 of them.
Listing them was /marks, which stopped at forty and said nothing about
distance, or about the ones nobody can reach.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands  # noqa: E402
from mud.mapper import Mapper  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def mark(store, name, room, kind, note):
    store.db.execute("INSERT OR REPLACE INTO landmark (name, room_id, kind, note) "
                     "VALUES (?, ?, ?, ?)", (name, room, kind, note))


def world():
    """Town -- two streets -- a shop and a guild; a house behind `home`; an
    area with no way in at all."""
    store = Store()
    town, street, shop = (store.add_room(n) for n in ("Town", "Street", "Shop"))
    guild, house, island = (store.add_room(n) for n in ("Guild", "House", "Island"))
    store.link(town, "n", street)
    store.link(street, "e", shop)
    store.link(street, "n", guild)
    store.link(town, "home", house)          # somebody's own; never routed
    mark(store, "shop", shop, "shop", "Town: the shop")
    mark(store, "guild", guild, "area", "Town: the guild")
    mark(store, "house", house, "misc", "Somebody's house")
    mark(store, "island", island, "area", "An island with no way in")
    m = Mapper(store)
    m.here = town
    return store, m, dict(town=town, street=street, shop=shop, guild=guild,
                          house=house, island=island)


def test_one_search_says_how_far_everything_is_as_the_router_would_walk():
    store, m, r = world()
    got = m.reach({r["shop"], r["guild"], r["house"], r["island"]})
    assert got == {r["shop"]: 2, r["guild"]: 2}
    for room in (r["shop"], r["guild"]):
        assert got[room] == len(m.route(room)), "the same walk /go would take"
    assert m.route(r["house"]) is None, "a personal way out is never routed"


def test_lost_means_no_distances():
    store, m, r = world()
    m.here = None
    assert m.reach({r["shop"]}) == {}


class Fake:
    def __init__(self, store, mapper):
        self.store, self.mapper = store, mapper


def run(text, store, m):
    said = []
    commands.handle(text, Fake(store, m), None, said.append)
    return said[0]


def test_speedruns_on_its_own_lists_each_kind_nearest_first():
    store, m, r = world()
    out = run("/speedruns", store, m)
    assert "4 places /go knows by name" in out
    assert "Areas -- 2, 1 you can reach" in out and "Shops -- 1, 1 you can reach" in out
    assert out.index("guild") < out.index("island"), "reachable before not"
    assert "2 steps" in out and "can't reach" in out


def test_speedruns_by_kind_or_word():
    store, m, r = world()
    out = run("/speedruns areas", store, m)
    assert out.startswith("Areas: 2") and "shop " not in out
    assert "Walk in once" in out, "says what to do about it"
    out = run("/speedruns town", store, m)
    assert "matching 'town': 2" in out
    assert run("/marks guild", store, m).startswith("matching 'guild'"), "the old name works"
    assert run("/speedruns shops", store, m).startswith("Shops: 1"), "a kind, by its plural"


def test_speedruns_when_lost_says_so_and_still_lists():
    store, m, r = world()
    m.here = None
    out = run("/speedruns", store, m)
    assert out.startswith("the map does not know where you are")
    assert "steps" not in out and "shop" in out


def test_the_marks_tab_is_sent_every_mark_with_its_distance():
    from mud.web import WebServer

    store, m, r = world()
    s = Session("127.0.0.1", 1, sec_code=12345,
                prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    s.store, s.mapper = store, m
    web = WebServer(s, port=0)
    pushed = []
    web.push = pushed.append
    web._marks_op({"t": "marks", "op": "list"})
    got = {x["name"]: x["steps"] for x in pushed[-1]["marks"]}
    assert got == {"shop": 2, "guild": 2, "house": None, "island": None}
    assert pushed[-1]["lost"] is False


def test_options_has_a_marks_tab_in_the_game_group():
    page = (UI / "index.html").read_text()
    rail = page[page.index('<nav id="opt-tabs">'):page.index("</nav>")]
    game = rail[rail.index("Game"):rail.index("Client")]
    assert 'data-tab="marks"' in game
    assert 'data-pane="marks"' in page and 'id="marks-list"' in page
    opts = (UI / "options.js").read_text()
    assert "'marks'" in opts and "window.refreshMarks" in opts
    js = (UI / "marks.js").read_text()
    assert "sendCommand(`/go ${m.name}`)" in js
    assert "window.options.query()" in js, "the search box filters it"
