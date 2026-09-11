"""A room has arrived once 3K's prompt follows it.

A room block used to count as arrived only when the next unrelated message
came.  Walking, that is the next room; standing in a quiet room it can be
seconds away.  The temple doorway after `embrace void` sent nothing for six
seconds, the look sent to find out where we were read as unanswered, and a
route standing at its own start said it could not reach it.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
from mud import session as session_module  # noqa: E402
from mud.session import Session  # noqa: E402


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


#: What 3K sends for a look in the doorway: the room's text, then its block.
DOORWAY = (b"-R-_Doorway to a temple. (doorway,leave)-R-_\r\n"
           b"You find yourself standing in mid-air.\r\n"
           + mip("DDD", "doorway~leave") + mip("HAB", "noun~portal~portal~exa #N")
           + mip("HAA", "npc~angel~An angel~kill #N") + b"\r\n")


def session(tmp):
    s = Session(sec_code=12345, jumpstart=False,
                prefixes_path=str(Path(tmp) / "p.json"))
    rooms = []
    s.bus.on(events.ROOM, lambda room: rooms.append(
        (sorted(room.exits), [m.name for m in room.mobs()])))
    return s, rooms


def test_a_room_has_arrived_once_its_prompt_follows():
    with tempfile.TemporaryDirectory() as tmp:
        s, rooms = session(tmp)
        s._consume(DOORWAY)
        assert rooms == [], "still open: its records may not all be in"
        s._consume(b">\r\n")
        assert rooms == [(["doorway", "leave"], ["angel"])]


def test_the_two_second_sample_is_still_not_a_room():
    with tempfile.TemporaryDirectory() as tmp:
        s, rooms = session(tmp)
        s._consume(mip("BAD", "Doorway to a temple. (doorway,leave)") + b"\r\n"
                   + mip("DDD", "doorway~leave") + b"\r\n>\r\n")
        assert rooms == []


def test_a_brief_room_is_finished_by_its_prompt_too():
    """Brief mode: the title and its contents, and no DDD.  The prompt says
    none is coming, without waiting for the title's timer."""
    with tempfile.TemporaryDirectory() as tmp:
        s, rooms = session(tmp)
        s._consume(b"-R-_Doorway to a temple. (doorway,leave)-R-_\r\n"
                   + mip("HAA", "npc~angel~An angel~kill #N") + b"\r\n>\r\n")
        assert rooms == [(["doorway", "leave"], ["angel"])]


def test_with_some_other_prompt_it_is_finished_when_things_go_quiet():
    with tempfile.TemporaryDirectory() as tmp:
        s, rooms = session(tmp)

        async def scenario():
            s._consume(DOORWAY)
            await asyncio.sleep(0.1)
            assert rooms == []
            await asyncio.sleep(session_module.ROOM_QUIET)
            assert rooms == [(["doorway", "leave"], ["angel"])]

        asyncio.new_event_loop().run_until_complete(scenario())
