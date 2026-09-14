"""The numpad as a way to walk, set up in Options -> Panels.

Off unless asked for; a grid of every key, each any command or several
separated by `;`; 5 is look and search.  The behaviour itself is exercised by
running numpad.js against a stand-in page -- these check that it is wired in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, events  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402

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


def test_numpad_is_a_command_an_alias_or_trigger_can_send():
    """The mode is the browser's, so /numpad asks every open window to change it."""
    s = Session("127.0.0.1", 1, sec_code=1)
    web = WebServer(s)
    pushed: list[dict] = []
    web.push = pushed.append
    web._wire_session()              # what start() does, without a socket
    said: list[str] = []
    for typed in ("/numpad off", "/numpad", "/numpad ON", "/numpad always", "/numpad sideways"):
        assert commands.handle(typed, s, None, said.append), typed
    assert pushed == [{"t": "numpad", "op": op} for op in ("off", "toggle", "on", "always")]
    assert said and "usage: /numpad" in said[-1]
    js = read("app.js")
    assert "m.t === 'numpad'" in js and "window.setNumpad(m.op)" in js
    assert "window.setNumpad = function (op)" in read("numpad.js")


def test_a_trigger_can_switch_it():
    """A rule's send that starts with / runs as the command would, typed."""
    import shutil
    import tempfile
    from mud.rules import RuleStore
    from mud.scripts import ScriptHost

    folder = Path(tempfile.mkdtemp())
    try:
        s = Session("127.0.0.1", 1, sec_code=1)
        s.send = lambda line: None
        pushed: list[dict] = []
        s.bus.on(events.PAGE, pushed.append)
        host = ScriptHost(s, folder)
        store = RuleStore(host, folder / "rules.json")
        host.rules = store
        _, err = store.upsert({"kind": "trigger", "pattern": "What would you like to buy",
                               "mode": "contains",
                               "actions": [{"type": "send", "text": "/numpad off"}]})
        assert err is None
        host._on_line("What would you like to buy?", "What would you like to buy?")
        assert pushed == [{"t": "numpad", "op": "off"}]
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_it_has_its_place_in_panels_and_is_loaded():
    page = read("index.html")
    for part in ('id="numpad-mode"', 'id="numpad-grid"', 'id="numpad-reset"',
                 'src="numpad.js"'):
        assert part in page, part
    assert page.index('src="app.js"') < page.index('src="numpad.js"')


def test_a_key_sends_exactly_as_typing_would():
    assert "window.sendCommand = (text) => send(text, true);" in read("app.js")
