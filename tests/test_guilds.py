"""The Guild.* packages, assembled.

3Scapes sends seven of them to a gentech, dozens of fields each, and the
field names belong to the guild rather than to the protocol: a gentech has
`hypergen_secs`, a viking has nothing of the sort.  So nothing here knows
what a field means.  What it has to get right is the assembling -- which
payloads replace, which add, and which are one answer sent in instalments.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.guilds import GuildFeed  # noqa: E402


def test_a_full_payload_replaces_and_a_bare_one_adds():
    """`full: 1` is the whole truth, so a field missing from it is a field
    the MUD has dropped.  Without it the payload is the bits that changed,
    and the rest stands."""
    f = GuildFeed()
    f.take("Guild.State", {"full": 1, "guild": "gentech",
                           "pu": 9393, "gexp": 421838, "medkits": 4})
    f.take("Guild.State", {"pu": 9400})
    assert f.packages["Guild.State"] == {
        "guild": "gentech", "pu": 9400, "gexp": 421838, "medkits": 4}
    f.take("Guild.State", {"full": 1, "guild": "gentech", "pu": 1})
    assert f.packages["Guild.State"] == {"guild": "gentech", "pu": 1}


def test_a_paged_answer_is_collected_rather_than_overwritten():
    """Guild.Progress arrives in pages, each marked `full`.  Taken at its
    word, page two would throw page one away and the panel would hold a
    third of the answer."""
    f = GuildFeed()
    f.take("Guild.Progress", {"full": 1, "pages": 3, "page": 1,
                              "guild": "gentech", "total_kills": 84})
    f.take("Guild.Progress", {"full": 1, "pages": 3, "page": 2,
                              "guild": "gentech", "num_died": 3})
    f.take("Guild.Progress", {"full": 1, "pages": 3, "page": 3,
                              "guild": "gentech", "quest_points": 870})
    assert f.packages["Guild.Progress"] == {
        "guild": "gentech", "total_kills": 84, "num_died": 3,
        "quest_points": 870}
    # And the next time round starts the set again rather than piling on.
    f.take("Guild.Progress", {"full": 1, "pages": 3, "page": 1,
                              "guild": "gentech", "total_kills": 90})
    assert f.packages["Guild.Progress"] == {"guild": "gentech",
                                            "total_kills": 90}


def test_how_to_read_a_payload_is_not_part_of_it():
    f = GuildFeed()
    f.take("Guild.Info", {"full": 1, "page": 1, "pages": 1,
                          "guild": "gentech", "echelon": 3})
    assert f.packages["Guild.Info"] == {"guild": "gentech", "echelon": 3}


def test_only_guild_packages_and_only_objects():
    f = GuildFeed()
    assert f.take("Char.Vitals", {"hp": 2023}) is False
    assert f.take("Guild.State", "not an object") is False
    assert f.take("Guild.State", None) is False
    assert f.packages == {}


def test_it_says_when_nothing_changed():
    """The screen is redrawn from this, so a payload that repeats what we
    already had should not cost a redraw."""
    f = GuildFeed()
    assert f.take("Guild.State", {"full": 1, "pu": 9393}) is True
    assert f.take("Guild.State", {"pu": 9393}) is False
    assert f.take("Guild.State", {"pu": 9394}) is True


def test_the_guild_is_whatever_the_packages_say_it_is():
    f = GuildFeed()
    assert f.guild == ""
    f.take("Guild.State", {"full": 1, "guild": "gentech", "pu": 1})
    assert f.guild == "gentech"


def test_a_new_connection_keeps_none_of_it():
    """Another character, possibly another guild, possibly the other game."""
    f = GuildFeed()
    f.take("Guild.State", {"full": 1, "guild": "gentech", "pu": 9393})
    f.clear()
    assert f.packages == {} and f.public() == {} and f.guild == ""


def test_three_kingdoms_hands_the_browser_nothing():
    """It does not speak GMCP at all, so the panel has nothing to hide
    behind -- it is simply not there."""
    assert GuildFeed().public() == {}


# --- where it lives ---------------------------------------------------------

def test_the_panel_sits_in_the_sidebar_directly_under_session():
    """With the rest of them, rather than over the output: the sidebar is
    where a panel you read alongside the text belongs."""
    from pathlib import Path as P
    ui = P(__file__).resolve().parents[1] / "mud" / "ui"
    page = (ui / "index.html").read_text()
    out = page[page.index('<div id="out">'):page.index('<div id="vitals">')]
    assert 'id="guildpanel"' not in out, "it does not sit over the output"
    side = page[page.index('<aside id="side">'):]
    order = [page[m:m + 40].split('"')[1] for m in
             (side.index(f'<section id="{name}"') + page.index('<aside id="side">')
              for name in ("session", "guildpanel"))]
    assert order == ["session", "guildpanel"]
    assert side.index('id="guildpanel"') < side.index('id="mapmon"'), \
        "under Session, and above the map"
    # Bounded, or a long guild pushes the map off the bottom of the column.
    rule = page[page.index("#guildpanel{"):page.index("}", page.index("#guildpanel{"))]
    assert "max-height" in rule and "overflow:auto" in rule


def test_it_rolls_up_by_its_heading_like_the_others():
    from pathlib import Path as P
    ui = P(__file__).resolve().parents[1] / "mud" / "ui"
    assert "'guildpanel'" in (ui / "panels.js").read_text()
    assert "#guildpanel.collapsed" in (ui / "index.html").read_text()
