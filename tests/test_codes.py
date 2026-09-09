"""Decoder tests, built from real 3k.org traffic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import codes  # noqa: E402

GLINE1 = "<cMthd>: <yTiger>    <cC>: <rOFF>    <cS>: <rOFF>    <cH>: <rOFF>    <cD>: <rOFF>"
GLINE2 = "G2N: <y81094877>    <cChi Focus>: <gNormal>    <yAE>: <g14>/83%"

# as it came off the wire, tags and values alternating
COMPOSITE = f"H~435~I~{GLINE1}~J~{GLINE2}"


def test_composite_alternates_tag_and_value():
    got, unknown = codes.parse_composite(COMPOSITE)
    assert unknown == []
    assert got["max_gp2"] == 435          # numeric, coerced
    assert got["gline1"] == GLINE1
    assert got["gline2"] == GLINE2


def test_composite_spec_example_corrected():
    """FFF A~312~C~300~E~57~L~75 -- the shape the wire actually uses."""
    got, unknown = codes.parse_composite("A~312~C~300~E~57~L~75")
    assert unknown == []
    assert got == {"hp": 312, "sp": 300, "gp1": 57, "enemy_pct": 75}


def test_composite_empty_value_clears_enemy():
    got, _ = codes.parse_composite("K~")
    assert got["enemy"] == ""


def test_gline_label_as_span():
    f = codes.parse_gline(GLINE1)
    assert f["Mthd"].value == "Tiger"
    assert f["Mthd"].colour == "yellow"
    # red is semantic: these guild toggles are off
    for k in ("C", "S", "H", "D"):
        assert f[k].value == "OFF"
        assert f[k].status == "bad"


def test_gline_label_as_plain_text_and_trailing_fragment():
    f = codes.parse_gline(GLINE2)
    assert f["G2N"].value == "81094877"
    assert f["Chi Focus"].value == "Normal"
    assert f["Chi Focus"].status == "good"
    # "<g14>/83%" -- the fragment after the span belongs to the value
    assert f["AE"].value == "14/83%"


def test_gline_plain_strips_markup():
    assert codes.gline_plain("<cMthd>: <yTiger>") == "Mthd: Tiger"


def test_haa_actions_resolve_to_commands():
    obj = codes.parse_haa(
        "npc~Marble Monolith~A huge marble monolith~"
        "exa #N/say hi, #N/consider #N/kill #N"
    )
    assert obj.kind == "npc"
    assert obj.name == "Marble Monolith"
    assert len(obj.actions) == 4
    # the MUD tells us which commands are valid for this object
    assert obj.command("kill") == "kill Marble Monolith"
    assert obj.command("consider") == "consider Marble Monolith"
    assert obj.command("eat") is None


def test_tell_flag_is_literal_x():
    t = codes.parse_bab("x~Buddy~moo")
    assert t.from_me and t.who == "Buddy" and t.message == "moo"
    assert codes.parse_bab("~Buddy~moo").from_me is False


def test_ddd_empty_is_still_a_room_change():
    assert codes.parse_ddd("") == []
    assert codes.parse_ddd("N E NE U") == ["n", "e", "ne", "u"]


def test_escape_sequence_restores_literal_tilde():
    assert codes.unescape("a^^b") == "a~b"
    assert codes.fields("grey_elf~Gray^^Elf") == ["grey_elf", "Gray", "Elf"]


# --- shapes taken from a real 3k.org session --------------------------------

def test_ddd_is_tilde_delimited_on_the_wire():
    """Spec and Portal both say spaces; 3k.org sends tildes."""
    assert codes.parse_ddd("w~d~u") == ["w", "d", "u"]
    assert codes.parse_ddd("e~w~s~n~d~omp~jump") == [
        "e", "w", "s", "n", "d", "omp", "jump",
    ]
    assert codes.parse_ddd("n e ne u") == ["n", "e", "ne", "u"]   # tolerate both


def test_haa_kinds_seen_in_the_wild():
    item = codes.parse_haa("item~coins~A single gold coin~get #N/exa #N")
    assert item.kind == "item"
    assert item.command("get") == "get coins"

    who = codes.parse_haa(
        "player~Grot~Grot the Master of Autumn (saintly)~exa #N/follow #N/say hi, #N"
    )
    assert who.kind == "player"
    assert who.command("follow") == "follow Grot"


def test_hab_is_scenery():
    noun = codes.parse_hab("noun~street~street~exa #N/search #N")
    assert noun.kind == "noun"
    assert noun.command("search") == "search street"


def test_inbound_tell_has_an_empty_flag():
    """Outbound is "x"; inbound is empty -- confirmed on the wire."""
    t = codes.parse_bab("~Friend~do you need an xmute?")
    assert t.from_me is False and t.who == "Friend"
    assert codes.parse_bab("x~Buddy~moo").from_me is True


def test_chat_channel_fields():
    c = codes.parse_caa("ctell~Clan Sa~Friend~[Clan] Friend : moo")
    assert (c.command, c.channel, c.who) == ("ctell", "Clan Sa", "Friend")


def test_gline_value_outside_a_span():
    """<gSA> : 5/5  -- the value is plain text in the following literal."""
    f = codes.parse_gline("<gSA> : 5/5 <gConf> : <bRock Solid>")
    assert f["SA"].value == "5/5"
    assert f["Conf"].value == "Rock Solid"
    assert f["Conf"].colour == "blue"


def test_composite_tolerates_undocumented_tags():
    got, unknown = codes.parse_composite("A~31207~B~30013~N~0~K~~E~6575~Z~9")
    assert got["hp"] == 31207          # far beyond the documented 0-9999
    assert got["enemy"] == ""          # K~~ clears the enemy
    assert got["round"] == 0           # N was undocumented until we saw the wire
    assert unknown == ["Z"]            # anything still unknown is reported, not fatal


def test_composite_round_counter():
    """N is a combat round counter -- undocumented, found on the wire."""
    got, unknown = codes.parse_composite("A~30013~N~7~L~47")
    assert unknown == []
    assert got["round"] == 7
    # combat ending: counter resets and the enemy clears together
    got, _ = codes.parse_composite("A~30013~N~0~K~")
    assert got["round"] == 0 and got["enemy"] == ""


def test_enemy_condition_markers_split_from_the_name():
    name, marks = codes.parse_enemy(
        "Gabriel, archangel of Yesod {glowing} [scratched]"
    )
    assert name == "Gabriel, archangel of Yesod"
    assert marks == ["glowing", "scratched"]
    assert codes.parse_enemy("a goblin") == ("a goblin", [])


def test_bad_yields_a_name_without_its_exits():
    from mud.codes import parse_bad

    assert parse_bad("The Center of Town (e,w,s,n,d,omp,jump)") == (
        "The Center of Town", ["e", "w", "s", "n", "d", "omp", "jump"]
    )
    assert parse_bad("North lane") == ("North lane", [])


def test_a_room_whose_name_ends_in_a_bracket_keeps_it():
    """'Behind the curtains (stage left front)' is a name, not a name plus an
    exit list, and cutting it would leave a room called something it isn't."""
    from mud.codes import parse_bad

    assert parse_bad("Behind the curtains (stage left front)") == (
        "Behind the curtains (stage left front)", []
    )


def test_a_title_cut_off_mid_exit_list_still_yields_the_name():
    """3K pads the title to a fixed width and cuts it there, so a long room
    name arrives with its exit list beheaded.  Left welded on, the name
    matches nothing and the map gains a room it already had."""
    from mud.codes import parse_bad

    assert parse_bad(
        "Pinnacle Theatre Side Entrance (guild,n,chaos,fantasy,sci,gy"
    ) == ("Pinnacle Theatre Side Entrance", [])


def test_a_truncated_sentence_is_not_mistaken_for_exits():
    from mud.codes import parse_bad

    assert parse_bad("A room (with a half sentence") == (
        "A room (with a half sentence", [])
