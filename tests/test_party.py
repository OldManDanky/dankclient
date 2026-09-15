"""A stepper leaves a stranger's mob alone, and shares a partymate's.

In a public area somebody not in your party is on their own hunt, and a
stepper that kills what they came for is stealing it.  A partymate's kill is
yours to share.  3K's room data does not say which a player is, so the party
is read from `pwho` and 3K's [PARTY] lines.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import botstore  # noqa: E402
from mud.botstore import RouteStore  # noqa: E402
from mud.codes import Chat  # noqa: E402
from mud.party import Party  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402

PWHO = ["Name         Location                                  Creator",
        "Friend       The Center of Town (e,w,s,n,d,omp,jump)  (mud        )",
        "Buddy        A Dark Square (n)                          (mud        )",
        ">"]


class FakeWriter:
    def write(self, data): pass


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


# --- reading the party ---------------------------------------------------------

def test_pwho_is_the_party():
    party = Party()
    for line in PWHO:
        party.line(line)
    assert party.members == {"friend", "buddy"}


def test_a_later_pwho_replaces_it():
    party = Party()
    for line in PWHO:
        party.line(line)
    for line in [PWHO[0], PWHO[1], ">"]:
        party.line(line)
    assert party.members == {"friend"}


def test_joins_and_leaves_keep_it_current():
    party = Party(me=lambda: "Player")
    party.line("[PARTY] Friend joins the party.")
    party.line("[PARTY] Buddy joins the party.")
    party.line("[PARTY] Buddy is being booted from the party.")
    assert party.members == {"friend", "buddy"}, "not gone until it is done"
    party.line("[PARTY] Buddy has been booted from the party.")
    party.line("[PARTY] Lost our leader!")
    party.line("[PARTY] New leader for the party: friend.")
    assert party.members == {"friend"}
    party.line("[PARTY] Friend has quit the party.")
    assert party.members == set()


def test_when_it_is_you_who_quits_there_is_no_party():
    party = Party(me=lambda: "Player")
    for line in PWHO:
        party.line(line)
    party.line("[PARTY] Player has quit the party.")
    assert party.members == set()


def test_somebody_on_the_party_channel_is_in_it():
    party = Party()
    party.chat(Chat(command="ptell", channel="Party", who="friend",
                    message="heading to the zodiacs"))
    party.chat(Chat(command="chat", channel="Newbie", who="Other", message="hi"))
    party.chat(Chat(command="ptell", channel="Party", who="buddy",
                    message="[PARTY] GOLD divvy called by buddy."))
    assert party.members == {"friend"}, "talk counts; 3K's announcements do not"


def test_an_announcement_does_not_put_back_somebody_who_left():
    """3K's [PARTY] lines carry a speaker, and after a quit it may be the one
    who quit: "Lost our leader!" must not count them back in."""
    party = Party(me=lambda: "Player")
    party.line("[PARTY] Friend joins the party.")
    party.chat(Chat(command="ptell", channel="Party", who="friend",
                    message="[PARTY] Friend has quit the party."))
    party.chat(Chat(command="ptell", channel="Party", who="friend",
                    message="[PARTY] Lost our leader!"))
    assert not party.has("Friend")


def test_the_session_reads_it_as_3k_sends_it():
    s = Session("127.0.0.1", 1, sec_code=12345)
    s._consume(("\r\n".join(PWHO) + "\r\n").encode())
    assert s.party.has("Friend") and s.party.has("buddy")
    s._consume(mip("CAA", "ptell~Party~pal~[PARTY] Pal joins the party.") + b"\r\n")
    assert s.party.has("Pal")


# --- what a stepper does about it ------------------------------------------------

def build(tmp):
    s = Session("127.0.0.1", 1, sec_code=12345)
    s.sent = []
    s._writer = FakeWriter()
    s.send = s.sent.append
    s.queue._send = s.sent.append
    s.me = "Player"
    host = ScriptHost(s, tmp)
    host.routes = RouteStore(host, Path(tmp) / "routes.json")
    host.routes.rest = 0.0          # the panel's rest, off so these run at speed
    return s, host


def hunt_with(s, host, player, answer=None, wait=0.4):
    """Start a hunt and arrive in a room with a rat and `player` in it."""
    route, _ = host.routes.upsert({"name": "hunt", "path": "n e", "targets": ["rat"]})

    async def scenario():
        host.routes.start(route.id)
        await asyncio.sleep(0)
        s._consume(mip("DDD", "s~e")
                   + (mip("HAA", f"player~{player}~{player} the Brave~exa #N") if player else b"")
                   + mip("HAA", "npc~rat~A leaping rat~kill #N"))
        s._consume(mip("FFF", "A~100"))
        await asyncio.sleep(0.05)
        if answer:
            s._consume(("\r\n".join(answer) + "\r\n").encode())
        await asyncio.sleep(wait)
    was = botstore.ASK_WAIT
    botstore.ASK_WAIT = 0.2
    try:
        asyncio.new_event_loop().run_until_complete(scenario())
    finally:
        botstore.ASK_WAIT = was
    return host.bots.bots["hunt"]


def test_a_stranger_s_mob_is_left_and_the_stepper_moves_on():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        bot = hunt_with(s, host, "Other")
        assert "pwho" in s.sent, "it asked who is in the party"
        assert "kill rat" not in s.sent
        assert "e" in s.sent, "and moved on"
        assert "Other" in bot.note and "not in your party" in bot.note


def test_a_partymate_s_kill_is_shared():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        for line in PWHO:
            s.party.line(line)
        s.party.asked()
        hunt_with(s, host, "Friend")
        assert "kill rat" in s.sent
        assert "pwho" not in s.sent, "no need to ask about somebody known"


def test_pwho_s_answer_is_waited_for():
    """Somebody the list does not know yet -- joined before the client was
    watching -- and pwho says they are in the party."""
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        hunt_with(s, host, "Friend", answer=PWHO)
        assert "pwho" in s.sent and "kill rat" in s.sent


def test_alone_with_the_rat_it_just_fights_and_asks_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        s, host = build(tmp)
        hunt_with(s, host, None)
        assert "kill rat" in s.sent and "pwho" not in s.sent


def test_it_does_not_ask_in_every_room():
    """A stranger following you from room to room is one pwho, not one a room."""
    party = Party(clock=lambda: 100.0)
    party.asked()
    assert party.since_asked() == 0.0
    assert botstore.ASK_EVERY >= 30
