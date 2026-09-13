"""Colouring the messages window: right-click a line, pick a colour.

The colour sticks to the channel or to the person, not to the one line -- a
single coloured line scrolls away -- and a person's colour wins over their
channel's.  Kept in the browser, with the rest of the window's preferences.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def chat() -> str:
    return (UI / "chat.js").read_text()


def test_a_line_opens_the_colour_menu_on_right_click():
    js = chat()
    assert "row.oncontextmenu" in js and "openMenu(e.clientX, e.clientY, m)" in js
    assert "e.preventDefault()" in js, "or the browser's own menu opens instead"


def test_colours_are_kept_with_the_windows_preferences():
    assert "store.set(`cm:${ID}:colours`" in chat()


def test_a_persons_colour_wins_over_their_channels():
    js = chat()
    body = js[js.index("function colourOf"):]
    body = body[:body.index("}")]
    assert body.index("colours.who") < body.index("colours.channel")


def _lum(hexa: str) -> float:
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _block(name: str) -> str:
    js = chat()
    start = js.index(f"const {name} =")
    return js[start:js.index("}" if name == "DARKER" else "];", start)]


def test_every_colour_reads_on_the_dark_ground():
    """A colour you cannot read is worse than none: each must be light."""
    palette = re.findall(r"'#([0-9a-f]{6})'", _block("PALETTE"))
    assert len(palette) == 8, palette
    for hexa in palette:
        assert _lum(hexa) > 0.45, hexa


def test_on_a_light_ground_each_has_a_darker_twin():
    """Options -> Colours can make the window light, and those same colours
    would all but vanish on it."""
    palette = re.findall(r"'#([0-9a-f]{6})'", _block("PALETTE"))
    twins = dict(re.findall(r"'#([0-9a-f]{6})':\s*'#([0-9a-f]{6})'", _block("DARKER")))
    assert set(twins) == set(palette), "every colour has one"

    def relative(hexa: str) -> float:          # WCAG's, not the rough one above
        def channel(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (channel(int(hexa[i:i + 2], 16) / 255) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for dark in twins.values():
        contrast = 1.05 / (relative(dark) + 0.05)   # against white
        assert contrast >= 4.5, (dark, round(contrast, 2))


def test_the_menu_can_be_closed_without_choosing():
    js = chat()
    assert "'Escape'" in js and "'mousedown', outside" in js


def test_the_menu_has_its_styles():
    assert ".cm-menu{" in (UI / "index.html").read_text()


def test_clear_empties_the_history_a_reload_would_bring_back():
    s = Session(prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    s.world.messages.append({"kind": "tell", "who": "Buddy", "text": "psst"})
    web = WebServer(s)
    assert web.snapshot()["messages"]
    web._on_client_message(b'{"t": "messages", "op": "something else"}')
    assert web.snapshot()["messages"], "only clear clears"
    web._on_client_message(b'{"t": "messages", "op": "clear"}')
    assert web.snapshot()["messages"] == []
