"""Getting started: the things worth doing once per character, ticked as done.

A new player used to get the map and nothing else.  The page works out which
steps are done rather than asking -- the markers above all, which are "on"
once a room title arrives wrapped in them.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.session import Session  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


def session(tmp, who="Player"):
    char = Path(tmp) / "profiles" / who
    char.mkdir(parents=True, exist_ok=True)
    return Session(sec_code=12345, jumpstart=False,
                   prefixes_path=str(char / "prefixes.json"))


def test_markers_are_on_once_a_marked_title_arrives():
    with tempfile.TemporaryDirectory() as tmp:
        s = session(tmp)
        assert s.markers_state() == "unknown"
        s._consume(b"-R-_North of Center (e,w)-R-_\r\n")
        assert s.markers_state() == "on"


def test_markers_are_off_after_rooms_with_no_marked_title():
    with tempfile.TemporaryDirectory() as tmp:
        s = session(tmp)
        for _ in range(3):
            s._consume(b"North of Center (e,w)\r\n" + mip("DDD", "e~w")
                       + mip("FFF", "A~100"))
        assert s.markers_state() == "off"


def test_a_character_switch_asks_again():
    with tempfile.TemporaryDirectory() as tmp:
        s = session(tmp)
        s._consume(b"-R-_North of Center (e,w)-R-_\r\n")
        other = Path(tmp) / "profiles" / "Other"
        other.mkdir()
        s.reload_prefixes(other / "prefixes.json")
        assert s.markers_state() == "unknown"


def test_done_is_kept_for_each_character():
    with tempfile.TemporaryDirectory() as tmp:
        s = session(tmp)
        assert s.start_done is False
        s.set_start_done(True)
        assert session(tmp).start_done is True
        assert session(tmp, "Other").start_done is False


def test_the_page_is_told_every_step():
    from mud.web import WebServer

    with tempfile.TemporaryDirectory() as tmp:
        s = session(tmp)
        web = WebServer(s, port=0)
        pushed = []
        web.push = pushed.append
        web._start_op({"t": "start", "op": "state"})
        got = pushed[-1]
        for key in ("done", "live", "data", "colours", "markers", "brief", "gags_on"):
            assert key in got, key
        assert got["markers"] == "unknown" and got["done"] is False
        web._start_op({"t": "start", "op": "done", "on": True})
        assert pushed[-1]["done"] is True and s.start_done is True
        assert web.snapshot()["start"] == {"done": True, "live": False}


def test_the_page_is_first_in_options_and_opens_itself():
    page = (UI / "index.html").read_text()
    rail = page[page.index('<nav id="opt-tabs">'):page.index("</nav>")]
    assert rail.index('data-tab="start"') < rail.index("opt-group"), "top of the rail"
    for step in ("gs-data", "gs-colours", "gs-markers", "gs-brief", "gs-extras"):
        assert f'id="{step}"' in page, step
    js = (UI / "start.js").read_text()
    assert "window.maybeGetStarted" in js and "s.done || !s.live" in js
    assert "'/prefixes set' : '/prefixes'" in js, "show first, then send"
    assert "window.maybeGetStarted(s.start)" in (UI / "app.js").read_text()
    assert ".gs{display:block;" in page, "each step stacked, not the room list's flex row"
