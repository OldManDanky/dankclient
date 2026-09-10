"""Options -> Fonts: the terminal's font, size and line spacing, and the size
of the messages window.  Kept in the browser, and applied from the first frame.
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def read(name: str) -> str:
    return (UI / name).read_text()


def test_there_is_a_fonts_tab_and_pane():
    page = read("index.html")
    assert 'data-tab="fonts"' in page and 'data-pane="fonts"' in page


def test_it_loads_after_the_terminal_it_changes():
    page = read("index.html")
    assert page.index('src="app.js"') < page.index('src="fonts.js"')


def test_the_terminal_starts_in_the_chosen_font():
    """Not the default for a moment and then the choice."""
    js = read("app.js")
    create = js[js.index("new Terminal("):]
    create = create[:create.index("});")]
    assert "font:family" in create and "font:size" in create and "font:line" in create


def test_changing_the_font_measures_a_column_again():
    """refit() keeps the width of a column; a new font makes that stale."""
    js = read("app.js")
    body = js[js.index("window.setTerminalFont"):]
    body = body[:body.index("};")]
    assert "perCol = 0" in body and "refit()" in body


def test_the_command_box_and_messages_follow_it():
    page = read("index.html")
    style = page[page.index("<style>"):page.index("</style>")]
    assert "font:var(--term-size)/1.4 var(--term-font)" in style      # #cmd
    assert "font:var(--cm-size)/1.45 var(--term-font)" in style       # messages


def test_only_installed_fixed_width_fonts_are_offered():
    js = read("fonts.js")
    assert "KNOWN.filter(installed)" in js
    assert "function fixedWidth" in js


def test_a_font_name_cannot_break_out_of_the_css():
    """It goes into a font-family string; a quote or a brace would end it."""
    assert "replace(/[\"\\\\;{}]/g" in read("app.js")
    assert "replace(/[\"\\\\;{}]/g" in read("fonts.js")
