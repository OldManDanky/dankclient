"""`/go` when the map does not know where you are.

It used to refuse and tell you to walk a room.  A look is cheaper than a walk
and safer than one: a room's exits and scenery are usually a unique
fingerprint, so looking is how the map finds itself again.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import commands, events  # noqa: E402
from mud.mapper import Mapper  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.store import Store  # noqa: E402


class FakeWriter:
    def write(self, data): pass


def mip(code, body, sec="12345"):
    d = f"{code}{body}"
    return f"#K%{sec}{len(d):03d}{d}".encode("latin-1")


def build():
    s = Session("127.0.0.1", 1, sec_code=12345)
    s.sent = []
    s._writer = FakeWriter()
    s.send = s.sent.append
    s.queue._send = s.sent.append
    store = Store()
    s.store = store
    s.mapper = Mapper(store)
    s.bus.on(events.ROOM, s._on_room)
    notes = []
    return s, store, notes.append, notes


def two_rooms(s, store):
    """A square you can see, and a bank north of it."""
    square = store.add_room("Square")
    bank = store.add_room("Bank")
    store.observe(square, ["n", "e"], ["fountain"])
    store.observe(bank, ["s"], ["vault"])
    store.link(square, "n", bank)
    store.link(bank, "s", square)
    store.db.execute("INSERT INTO landmark (name, room_id, note) VALUES (?,?,?)",
                     ("bank", bank, "the bank"))
    return square, bank


def test_go_looks_before_it_gives_up():
    s, store, note, notes = build()
    square, bank = two_rooms(s, store)
    s.mapper.here = None                        # lost

    async def scenario():
        commands.handle("/go bank", s, None, note)
        await asyncio.sleep(0)
        assert s.sent == ["l"], f"a look, not a refusal: {s.sent} {notes}"
        # The square answers, and it is the only room shaped like that.
        s._consume(mip("DDD", "n~e") + mip("HAB", "noun~fountain~fountain~exa #N"))
        s._consume(mip("FFF", "A~100"))
        await asyncio.sleep(0.05)
        assert s.mapper.here == square, "the look found us"
        assert any("walking" in n for n in notes), notes

    asyncio.new_event_loop().run_until_complete(scenario())


def test_a_look_that_does_not_find_us_says_so():
    s, store, note, notes = build()
    two_rooms(s, store)
    s.mapper.here = None

    async def scenario():
        commands.handle("/go bank", s, None, note)
        await asyncio.sleep(0)
        assert s.sent == ["l"]
        await asyncio.sleep(2.1)                # nothing comes back
        assert any("still lost" in n for n in notes), notes

    asyncio.new_event_loop().run_until_complete(scenario())
