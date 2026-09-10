"""3kdb's gag library: taken with the map, switched on a group at a time.

Seven hundred-odd tt++ #gag lines in common/gags/, by group.  Every group
starts off -- a gag hides text, and nobody should lose a line they wanted to
read without saying so -- and which are on belongs to the character.  The
patterns below are 3kdb's own.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import gaglib, update  # noqa: E402
from mud.session import Session  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"

AREA = """#NOP -- Mud Area Gags;
#alias _gag_combat_area {
    #if $gags[combat_area] {
        #class gags_combat_area open;

        #NOP -- Aegis Global;
        #gag {^The zombie viciously bites you!$};
        #gag {One of the sentry's grenades explodes, enveloping you in a};
        #NOP -- Carebears;
        #gag {^You aim and fire at %*. A beam of bright blue light shoots};
        #act {^The brilliant sphere flashes brightly.} {#line gag};
    };
};
"""

RAYGUN = """#class gags_combat_items open;
#gag {^%w grunts as %1 hits %d times.$};
#gag {^100%a sure};
"""


def test_tt_patterns_become_regexes_that_mean_the_same():
    import re

    def hits(tt, line):
        return bool(re.search(gaglib.translate(tt), line))

    assert hits("^The zombie viciously bites you!$", "The zombie viciously bites you!")
    assert not hits("^The zombie viciously bites you!$", "The zombie viciously bites you!!")
    assert hits("^You aim and fire at %*. A beam", "You aim and fire at a rat. A beam of light")
    assert not hits("^You aim and fire at %*. A beam", "Then: You aim and fire at x. A beam")
    assert hits("One of the sentry's grenades", "Oh! One of the sentry's grenades explodes")
    assert hits("^%w grunts as %1 hits %d times.$", "Cur grunts as the sword hits 3 times.")
    assert not hits("^%w grunts as %1 hits %d times.$", "Cur grunts as the sword hits many times.")
    # Braces are tt++ handing a regex through, as 3kdb uses them.
    assert hits("{Tugs|Hugs} cringes in terror.", "Hugs cringes in terror.")
    assert hits("^did {no|minimal|some} damage{.|!}$", "did minimal damage!")
    assert hits("{^The Spork Lance GASHES (.*)\\!}", "The Spork Lance GASHES the orc!")
    assert hits("^You hit %%1 hard.$", "You hit the orc hard."), "%%1 in an alias"
    assert gaglib.translate("^100%a sure") is None, "a code it does not know"


def test_only_the_gags_are_taken_with_their_headings():
    gags, skipped = gaglib.parse(AREA)
    assert [g["section"] for g in gags] == ["Aegis Global", "Aegis Global", "Carebears"]
    assert not any("sphere" in g["pattern"] for g in gags), "an #act is a script"
    assert skipped == 0


def library(tmp):
    root = Path(tmp) / "3kdb"
    (root / "common" / "gags").mkdir(parents=True)
    (root / "common" / "gags" / "gags_area.tin").write_text(AREA)
    (root / "common" / "gags" / "gags_raygun.tin").write_text(RAYGUN)
    out = Path(tmp) / "scripts" / gaglib.LIBRARY
    out.parent.mkdir()
    return gaglib.import_gags(root, out), out


def test_the_library_is_read_into_groups_and_counts_what_it_left_out():
    with tempfile.TemporaryDirectory() as tmp:
        did, out = library(tmp)
        assert did == {"groups": 2, "gags": 4, "skipped": 1}
        lib = gaglib.load_library(out)
        assert [g["key"] for g in lib["groups"]] == ["area", "raygun"]
        assert lib["groups"][0]["sections"] == ["Aegis Global", "Carebears"]


def session(tmp, who="Player"):
    char = Path(tmp) / "profiles" / who
    char.mkdir(parents=True, exist_ok=True)
    s = Session(prefixes_path=str(char / "prefixes.json"))
    s.gaglib_path = Path(tmp) / "scripts" / gaglib.LIBRARY
    return s


def test_every_group_starts_off_and_is_switched_on_by_the_character():
    with tempfile.TemporaryDirectory() as tmp:
        library(tmp)
        s = session(tmp)
        s.apply_gag_groups()
        assert not s.is_gagged("The zombie viciously bites you!"), "off to start"
        assert s.set_gag_group("area", True) == 3
        assert s.is_gagged("The zombie viciously bites you!")
        assert not s.is_gagged("Cur grunts as the sword hits 3 times."), "only that group"
        again = session(tmp)
        again.apply_gag_groups()
        assert again.is_gagged("The zombie viciously bites you!"), "kept for them"
        other = session(tmp, "Other")
        other.apply_gag_groups()
        assert not other.is_gagged("The zombie viciously bites you!"), "not for others"
        s.set_gag_group("area", False)
        assert not s.is_gagged("The zombie viciously bites you!")


def test_a_character_switch_brings_their_groups():
    with tempfile.TemporaryDirectory() as tmp:
        library(tmp)
        s = session(tmp, "Player")
        s.set_gag_group("raygun", True)
        other = Path(tmp) / "profiles" / "Other"
        other.mkdir()
        s.reload_prefixes(other / "prefixes.json")
        assert not s.is_gagged("Cur grunts as the sword hits 3 times.")
        s.reload_prefixes(Path(tmp) / "profiles" / "Player" / "prefixes.json")
        assert s.is_gagged("Cur grunts as the sword hits 3 times.")


def test_the_options_tab_is_sent_each_group_and_can_switch_it():
    from mud.web import WebServer

    with tempfile.TemporaryDirectory() as tmp:
        library(tmp)
        s = session(tmp)
        web = WebServer(s, port=0)
        pushed = []
        web.push = pushed.append
        web._gaglib_op({"t": "gaglib", "op": "list"})
        area = pushed[-1]["groups"][0]
        assert area["title"] == "Combat: area monsters" and area["count"] == 3
        assert area["on"] is False and area["gags"][0].startswith("^The zombie")
        web._gaglib_op({"t": "gaglib", "op": "set", "key": "area", "on": True})
        assert pushed[-1]["groups"][0]["on"] is True
        assert s.is_gagged("The zombie viciously bites you!")


def test_it_comes_with_the_map_and_the_bots():
    assert update.WANTED["gags"] == "common/gags"
    assert update.IMPORTERS["gags"] >= 1


def test_gags_are_their_own_page_not_triggers():
    """/gag's gags are kept as rules, as ever, but listed under Options ->
    Gags.  A trigger that sends commands and hides its line is still a
    trigger, and stays among them."""
    js = (UI / "rules.js").read_text()
    assert "window.renderOwnGags(cache.rules.filter(plainGag))" in js
    assert "&& !plainGag(r)" in js, "left out of the triggers list"
    assert "!(r.actions && r.actions.length)" in js, "only the ones that do nothing else"
    page = (UI / "index.html").read_text()
    assert 'data-tab="gaglib">Gags<' in page
    pane = page[page.index('data-pane="gaglib"'):]
    pane = pane[:pane.index("</section>")]
    assert pane.index('id="gag-own"') < pane.index('id="gaglib-list"'), "yours first"
    g = (UI / "gaglib.js").read_text()
    assert "gag: true, actions: [], enabled: true" in g, "the same rule /gag makes"
    assert "op: 'delete', id: g.id" in g


def test_options_has_a_gag_library_tab_in_automation():
    page = (UI / "index.html").read_text()
    rail = page[page.index('<nav id="opt-tabs">'):page.index("</nav>")]
    auto = rail[rail.index("Automation"):rail.index("Interface")]
    assert 'data-tab="gaglib"' in auto
    assert 'id="gaglib-list"' in page and '<script src="gaglib.js">' in page
    js = (UI / "gaglib.js").read_text()
    assert "op: 'set', key: g.key, on: box.checked" in js
    assert "window.refreshGaglib" in (UI / "options.js").read_text()
    assert "done.gags" in (UI / "updates.js").read_text()
