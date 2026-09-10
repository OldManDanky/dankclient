"""The numpad as a way to walk, set up in Options -> Panels.

Off unless asked for; a grid of every key, each any command or several
separated by `;`; 5 is look and search.  The behaviour itself is exercised by
running numpad.js against a stand-in page -- these check that it is wired in.
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def read(name: str) -> str:
    return (UI / name).read_text()


def test_it_is_off_until_asked_for():
    assert "store.get('numpad:mode', 'off')" in read("numpad.js")


def test_five_looks_and_searches():
    assert "5: 'look;search'" in read("numpad.js")


def test_the_digit_row_is_never_involved():
    """Keyed on the physical key, which says Numpad8 whatever NumLock says."""
    js = read("numpad.js")
    assert "KEYS[e.code]" in js and "Numpad8: '8'" in js


def test_holding_a_key_sends_once():
    assert "if (e.repeat) return true;" in read("numpad.js")


def test_it_has_its_place_in_panels_and_is_loaded():
    page = read("index.html")
    for part in ('id="numpad-mode"', 'id="numpad-grid"', 'id="numpad-reset"',
                 'src="numpad.js"'):
        assert part in page, part
    assert page.index('src="app.js"') < page.index('src="numpad.js"')


def test_a_key_sends_exactly_as_typing_would():
    assert "window.sendCommand = (text) => send(text, true);" in read("app.js")
