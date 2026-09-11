"""Dings: a sound for a tell or a channel line, chosen per channel or person.

Chosen in the messages window's right-click menu, beside the colours; the
sound is made by sound.js with the browser's own audio.  Off until chosen.
The behaviour is exercised by running both files against a stand-in page;
these check the wiring.
"""

from __future__ import annotations

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def read(name: str) -> str:
    return (UI / name).read_text()


def test_nothing_dings_until_chosen():
    assert "store.get(`cm:${ID}:dings`, '{}')" in read("chat.js")


def test_your_own_lines_and_hidden_channels_never_ding():
    js = read("chat.js")
    body = js[js.index("function wantsDing"):]
    body = body[:body.index("\n  }\n")]
    assert "isMine(m)" in body and "muted.has(" in body


def test_the_menu_offers_it_beside_the_colours():
    assert "menu.append(dingRow(m, channel));" in read("chat.js")


def test_a_tell_and_a_channel_sound_different():
    assert "tell: [880, 1318.5], channel: [659.3]" in read("sound.js")


def test_a_busy_channel_is_a_ding_not_a_buzzer():
    js = read("sound.js")
    assert "const GAP = 1.2;" in js and "now - last < GAP" in js


def test_3ks_bell_rings():
    """`wake` sends a BEL; xterm only announces it, so something has to listen.
    Nothing did, and the bell reached the terminal and made no sound."""
    assert "term.onBell(() => { if (window.ding) window.ding('bell'); });" in read("app.js")
    assert "bell: [1046.5, 1318.5, 1568]" in read("sound.js")
    assert "store.get('sound:bell', '1')" in read("sound.js"), "on unless switched off"


def test_an_old_bell_does_not_ring_again_after_a_refresh():
    """The scrollback put back after a refresh has control characters removed."""
    assert r"replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '')" in read("app.js")


def test_sounds_have_their_place_in_panels_and_are_loaded():
    page = read("index.html")
    for part in ('id="sound-volume"', 'id="sound-background"',
                 'id="sound-rows"', 'id="sound-error"',
                 'src="sound.js"'):
        assert part in page, part
