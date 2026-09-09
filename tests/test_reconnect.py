"""A link death is not the end of the session.

3k.org drops you for a reboot, for a bad hop, and for nothing at all.  The map,
the rules, the log and the browser on the other end of the websocket are all
still good when it does -- so the client goes back and picks the character up
again, and only the things the socket owned are thrown away.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events                                     # noqa: E402
from mud.session import Session                            # noqa: E402


def mip(body: str, sec: str = "12345") -> bytes:
    return f"#K%{sec}{len(body):03d}{body}".encode()


LOGIN = (b"<Entering 3Kingdoms.  Enter your character name or press enter "
         b"to continue>\r\nPassword: \r\n"
         b"3Kingdoms welcomes you back from linkdeath.\r\n")


class Char:
    """Just enough of profile.Character for the login to work from."""
    name = "Player"
    password = "hunter2"


async def flaky(*, drops: int, tail: bytes = b"", speak=None):
    """A MUD that hangs up on the first `drops` connections.

    Returns the session, everything each connection was told, and a running
    log of what the client said back -- one list per connection, because the
    question is always "did it do it *again*".
    """
    heard: list[list[bytes]] = []
    served = 0

    async def mud(reader, writer):
        nonlocal served
        served += 1
        mine: list[bytes] = []
        heard.append(mine)
        writer.write(LOGIN)
        if speak is not None:
            writer.write(speak(served))
        await writer.drain()
        if served <= drops:
            if tail:
                writer.write(tail)
                await writer.drain()
            # Long enough that the test can see the client holding half a
            # message before the hang-up lands.
            await asyncio.sleep(0.2 if tail else 0.05)
            writer.close()
            return
        while True:
            data = await reader.read(256)
            if not data:
                return
            mine.append(data)

    server = await asyncio.start_server(mud, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    session = Session("127.0.0.1", port, sec_code=12345)
    session.backoff_first = 0.05
    session.backoff_longest = 0.05
    session.character = Char()
    await session.connect()
    session.login.begin(Char.name, Char.password)
    return session, server, heard


async def _dropped_once() -> dict:
    session, server, heard = await flaky(drops=1)
    stay = asyncio.create_task(session.stay())
    await asyncio.sleep(0.6)
    out = {"connections": session.connections,
           "said": [b"".join(c) for c in heard],
           "connected": session.connected}
    stay.cancel()
    await session.aclose()
    server.close()
    return out


DROPPED = asyncio.run(_dropped_once())


def test_it_goes_back():
    assert DROPPED["connections"] == 2, DROPPED
    assert DROPPED["connected"]


def test_it_logs_the_character_back_in():
    """Both halves: the login clears the password, so the second name and
    password have to come from the character rather than from the login."""
    said = DROPPED["said"][-1]
    assert b"Player\r\n" in said, said
    assert b"hunter2\r\n" in said, said


def test_the_handshake_goes_out_again():
    """MIP is something the MUD does for a connection.  The new one has never
    heard of us, so an armed flag carried over would leave the client silent
    and every panel empty."""
    assert b"3klient 12345" in DROPPED["said"][-1]


# --- what the socket owned ---------------------------------------------------

async def _state_across_a_drop() -> dict:
    # Half a MIP message, cut off mid-body by the hang-up.  Glue it onto the
    # next connection and the scanner eats the whole login.
    half = b"#K%12345068FFFJ~G2N: <y810"
    session, server, heard = await flaky(drops=1, tail=half)

    class Bots:
        def __init__(self): self.stopped = 0
        def stop_all(self): self.stopped += 1; return 0
    session.bots = Bots()

    waits: list[float] = []
    session.bus.on(events.RETRYING, waits.append)

    stay = asyncio.create_task(session.stay())
    await asyncio.sleep(0.1)
    assert session._scanner.in_message, "the fixture did not cut a message"
    await asyncio.sleep(0.8)
    out = {"in_message": session._scanner.in_message,
           "mip_seen": session.mip_seen,
           "bots_stopped": session.bots.stopped,
           "waits": waits,
           "attempts": session.attempts,
           "retry_at": session.retry_at}
    stay.cancel()
    await session.aclose()
    server.close()
    return out


ACROSS = asyncio.run(_state_across_a_drop())


def test_half_a_message_does_not_cross_the_gap():
    assert not ACROSS["in_message"]


def test_the_bots_are_stopped():
    """A route walking somewhere carries on counting steps while there is no
    connection, and arrives believing it is somewhere it has never been."""
    assert ACROSS["bots_stopped"] >= 1


def test_it_says_it_is_retrying():
    """A client retrying silently looks exactly like one that has given up."""
    assert ACROSS["waits"] == [0.05]


def test_nothing_is_pending_once_it_is_back():
    assert ACROSS["attempts"] == 0
    assert ACROSS["retry_at"] == 0.0


def test_the_map_is_unsure_where_you_are():
    """You come back standing where you were -- usually.  Not always, and the
    mapper works it out from the first room block either way."""
    from mud.mapper import Mapper

    class FakeStore:
        locked = False
    m = Mapper(FakeStore())
    m.here = m._was = 1165
    m.candidates = [1165, 1166]
    m.sent("w")
    m._last_exits = ["n", "s"]
    m.unsure()
    assert m.here is None
    assert m.candidates == []
    assert not m._pending, "commands waiting to be blamed for a room block"
    assert m._last_exits == []
    assert m._was == 1165, "the best evidence about which room this is"


# --- backing off, and giving up ----------------------------------------------

async def _keeps_knocking() -> list[float]:
    waits: list[float] = []
    session, server, heard = await flaky(drops=3)
    session.backoff_first, session.backoff_longest = 0.02, 0.05
    session.bus.on(events.RETRYING, waits.append)
    stay = asyncio.create_task(session.stay())
    await asyncio.sleep(0.8)
    stay.cancel()
    await session.aclose()
    server.close()
    return waits


def test_it_backs_off_and_does_not_give_up():
    """No attempt limit: a reboot takes as long as it takes.  The wait is
    capped instead, so it keeps knocking without hammering."""
    waits = asyncio.run(_keeps_knocking())
    assert len(waits) == 3, waits
    assert waits == [0.02, 0.02, 0.02], waits   # each drop starts over


async def _no_reconnect() -> int:
    session, server, heard = await flaky(drops=1)
    session.reconnect = False
    await asyncio.wait_for(session.stay(), 2.0)   # returns, does not hang
    n = session.connections
    await session.aclose()
    server.close()
    return n


def test_reconnecting_can_be_switched_off():
    """--no-reconnect, and every replay of a capture: the end of the input is
    the end."""
    assert asyncio.run(_no_reconnect()) == 1


# --- what the browser is told ------------------------------------------------

def _fake_web(connected: bool, retry_in: float = 0.0):
    import time as _t
    from mud import web as webmod

    class FakeQueue:
        def now(self, line): sent.append(line)

    class FakeSession:
        connected = False
        reconnect = True
        attempts = 2
        retry_at = 0.0
        queue = FakeQueue()
        def send(self, line): sent.append(line)

    sent: list[str] = []
    notes: list[str] = []
    web = webmod.WebServer.__new__(webmod.WebServer)
    web.session = FakeSession()
    web.session.connected = connected
    web.session.retry_at = (_t.monotonic() + retry_in) if retry_in else 0.0
    web._clients = set()
    web.scripts = None
    web.note = notes.append
    return web, sent, notes


def test_typing_into_a_dead_connection_says_so():
    """Not a traceback out of the websocket loop, and not silence: the reason
    the terminal has stopped saying anything is the actual question."""
    import json
    web, sent, notes = _fake_web(connected=False)
    web._on_client_message(json.dumps({"t": "cmd", "d": "kill orc"}).encode())
    assert sent == []
    assert notes and "reconnecting" in notes[0], notes


def test_the_countdown_reaches_the_browser():
    web, _, _ = _fake_web(connected=False, retry_in=4.2)
    link = web._link()
    assert link == {"up": False, "attempts": 2, "in": 5, "reconnect": True}, link


def test_nothing_counts_down_while_it_is_up():
    web, _, _ = _fake_web(connected=True)
    assert web._link()["in"] == 0


# --- hanging up on purpose ---------------------------------------------------

async def _hang_up_and_come_back() -> dict:
    session, server, heard = await flaky(drops=0)
    waits: list[float] = []
    session.bus.on(events.RETRYING, waits.append)
    stay = asyncio.create_task(session.stay())
    await asyncio.sleep(0.15)

    session.hangup()
    await asyncio.sleep(0.4)         # far longer than the 0.05s backoff
    parked = {"up": session.connected, "connections": session.connections,
              "waits": list(waits), "stay_done": stay.done()}

    session.resume()
    await asyncio.sleep(0.25)
    back = {"up": session.connected, "connections": session.connections,
            "waits": list(waits)}

    stay.cancel()
    await session.aclose()
    server.close()
    return {"parked": parked, "back": back}


HANGUP = asyncio.run(_hang_up_and_come_back())


def test_a_hang_up_stays_hung_up():
    """A session that comes back two seconds after you press Disconnect is a
    session with a broken button."""
    assert HANGUP["parked"]["up"] is False
    assert HANGUP["parked"]["waits"] == [], "it tried to reconnect"
    assert HANGUP["parked"]["connections"] == 1


def test_the_client_outlives_the_hang_up():
    """What closes is the connection, not the window: the map, the log and
    everything in Options are still there to come back to."""
    assert not HANGUP["parked"]["stay_done"], "the read loop gave up and exited"


def test_asking_for_it_back_does_not_sit_through_a_backoff():
    """Somebody pressing Reconnect did not cause the wait and should not serve
    it -- so the countdown never appears on that path."""
    assert HANGUP["back"]["up"] is True
    assert HANGUP["back"]["connections"] == 2
    assert HANGUP["back"]["waits"] == [], HANGUP["back"]["waits"]


def _parked_session():
    """A real Session over a real Store, with no socket and no loop."""
    from mud.logbook import Logbook
    from mud.store import Store

    class Bare(Session):
        def __init__(self):            # __init__ wants a host and a port
            pass

    s, store = Bare(), Store(":memory:")
    s.wanted, s._writer, s._asked = True, None, asyncio.Event()
    s.store, s.logbook = store, Logbook(store)
    s.bots = type("B", (), {"stop_all": lambda self: None})()
    return s, store


def test_hanging_up_puts_the_log_on_disk():
    """The buffer holds a few seconds of history, and a few seconds is still
    history -- it must not be the part you lose by leaving tidily."""
    s, store = _parked_session()
    s.logbook.add("recv", "you are standing in The Trading Post")
    s.hangup()
    rows = store.db.execute("SELECT text FROM line").fetchall()
    assert [r["text"] for r in rows] == ["you are standing in The Trading Post"]
    assert s.wanted is False


def test_the_session_row_says_when_it_finished():
    """A row with no end never finished: the client was killed, or it
    link-died and nobody brought it back.  Worth telling apart afterwards."""
    s, store = _parked_session()
    sid = s.logbook.session_id

    def ended():
        return store.db.execute(
            "SELECT ended_at FROM session WHERE id = ?", (sid,)).fetchone()[0]

    assert ended() is None, "a running session has no end"
    s.hangup()
    assert ended() is not None
    s.resume()
    assert ended() is None, "it did not finish after all"


def test_the_session_row_says_who_played():
    """The client is up and logging before anybody has picked a character, so
    the row cannot be named when it is made."""
    s, store = _parked_session()
    s.logbook.played_by("Player")
    row = store.db.execute("SELECT character FROM session WHERE id = ?",
                           (s.logbook.session_id,)).fetchone()
    assert row["character"] == "Player"


def test_the_browser_is_told_which_kind_of_disconnect_it_is():
    """Waiting for it to come back and waiting for you to do something about
    it look identical on screen otherwise."""
    web, _, _ = _fake_web(connected=False)
    web.session.wanted = False
    assert web._link()["reconnect"] is False
    web.session.wanted = True
    assert web._link()["reconnect"] is True


def test_closing_the_window_saves_the_way_disconnect_does():
    """Same act, so it must be the same code path rather than a second one
    that drifts. And still no `quit`: closing the connection and logging the
    character out are different things."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "mud" / "__main__.py").read_text()
    shut = source[source.index("window closed"):]
    shut = shut[:shut.index("for task in")]
    assert "session.hangup()" in shut
    assert "quit" not in shut.lower()
    # and nothing anywhere sends one on the way out
    assert 'send("quit"' not in source and "send('quit'" not in source
