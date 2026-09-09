"""Full-stack test: fake MUD -> Session -> WebServer -> browser.

Uses a hand-rolled WebSocket client so the suite stays dependency-free.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.session import Session  # noqa: E402
from mud.web import WebServer, _accept_key, _frame, _read_frame  # noqa: E402


def mip(body: str, sec: str = "12345") -> bytes:
    return f"#K%{sec}{len(body):03d}{body}".encode()


#: The login as 3k.org actually runs it, because the handshake now waits for
#: it: the prompts are what tell the client it is allowed to speak.
LOGIN = (
    b"<Entering 3Kingdoms.  Enter your character name or press enter "
    b"to continue>\r\n"
    b"Password: \r\n"
    b"3Kingdoms welcomes you back from linkdeath.\r\n"
)

SCRIPT = (
    LOGIN
    + mip("DDDw~d~u")
    + mip("HAAnpc~Cur~Cur, the tradesman's dog~exa #N/consider #N/kill #N")
    + mip("HABnoun~street~street~exa #N/search #N")
    + mip("BADThe Trading Post (w,d,u)")
    + mip("FFFA~30013~B~30013~C~3971~D~3747~E~6575~F~12350")
    + mip("FFFK~Gabriel, archangel of Yesod {glowing}~L~86~N~3")
    + mip("CAActell~Clan Sa~Friend~[Clan] Friend : moo")
    + b"You are standing in The Trading Post.\r\n"
)


async def scenario() -> dict:
    got_from_client: list[bytes] = []

    async def mud(reader, writer):
        writer.write(SCRIPT)
        await writer.drain()
        while True:
            data = await reader.read(256)
            if not data:
                break
            got_from_client.append(data)

    mud_server = await asyncio.start_server(mud, "127.0.0.1", 0)
    mud_port = mud_server.sockets[0].getsockname()[1]

    session = Session("127.0.0.1", mud_port, sec_code=12345)
    await session.connect()
    web = WebServer(session, port=0)
    port = await web.start()
    reader_task = asyncio.create_task(session.run())

    await asyncio.sleep(0.25)          # let the script land

    # --- static file --------------------------------------------------------
    # urlopen blocks; calling it inline would deadlock the loop serving it.
    def fetch(url: str) -> bytes:
        return urllib.request.urlopen(url, timeout=5).read()

    html = (await asyncio.to_thread(fetch, f"http://127.0.0.1:{port}/")).decode()
    app = await asyncio.to_thread(fetch, f"http://127.0.0.1:{port}/app.js")

    # --- websocket handshake ------------------------------------------------
    r, w = await asyncio.open_connection("127.0.0.1", port)
    key = base64.b64encode(os.urandom(16)).decode()
    w.write(
        f"GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    await w.drain()
    head = await r.readuntil(b"\r\n\r\n")
    assert b"101" in head, head
    assert _accept_key(key).encode() in head, "bad Sec-WebSocket-Accept"

    _, payload = await _read_frame(r)
    snapshot = json.loads(payload)

    # --- browser sends a command -------------------------------------------
    body = json.dumps({"t": "cmd", "d": "kill Cur"}).encode()
    # client frames must be masked; a zero mask keeps the test readable
    frame = bytearray([0x81, 0x80 | len(body)]) + b"\x00\x00\x00\x00" + body
    w.write(bytes(frame))
    await w.drain()
    await asyncio.sleep(0.15)

    w.close()
    reader_task.cancel()
    await session.aclose()
    mud_server.close()
    return {
        "html": html,
        "app": app,
        "snapshot": snapshot,
        "to_mud": b"".join(got_from_client),
        "unknown": dict(session.world.unknown_codes),
    }


RESULT = asyncio.run(scenario())


def test_static_files_are_served():
    assert "<title>Dank Mud Client</title>" in RESULT["html"]
    # Inline, so the browser never asks: a favicon request is answered with a
    # 404 on every single load, and shows a broken icon in the tab.
    assert 'rel="icon" href="data:image/svg+xml,' in RESULT["html"]
    assert b"FitAddon" in RESULT["app"]


def test_snapshot_carries_player_state():
    p = RESULT["snapshot"]["player"]
    assert RESULT["snapshot"]["t"] == "state"
    assert p["hp"] == 30013 and p["max_hp"] == 30013
    assert p["hp_pct"] == 100.0
    assert p["round"] == 3
    assert p["enemy_pct"] == 86
    assert p["enemy"].startswith("Gabriel")


def test_snapshot_carries_the_room():
    room = RESULT["snapshot"]["room"]
    assert room["short"] == "The Trading Post (w,d,u)"
    assert room["exits"] == ["w", "d", "u"]
    assert [o["name"] for o in room["contents"]] == ["Cur"]
    assert [o["name"] for o in room["scenery"]] == ["street"]
    # action templates survive the trip to the browser
    assert "kill #N" in room["contents"][0]["actions"]


def test_handshake_and_commands_reach_the_mud():
    sent = RESULT["to_mud"]
    assert b"3klient 12345~" in sent      # fired once the login was behind us
    assert b"kill Cur\r\n" in sent        # browser -> python -> socket


def test_no_codes_fell_through_as_unknown():
    assert RESULT["unknown"] == {}


def test_accept_key_matches_the_rfc_vector():
    """Pin the handshake to RFC 6455 s1.3 rather than to our own constant.

    A wrong magic GUID yields a well-formed response that browsers reject
    without sending anything -- and a test that recomputes the accept value
    using the same constant will pass regardless.  Only a literal from the
    spec catches it.
    """
    from mud.web import _accept_key

    assert _accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_frame_headers_are_well_formed():
    from mud.web import _frame

    assert _frame(b"x" * 5)[:2].hex() == "8105"          # 7-bit length
    assert _frame(b"x" * 126)[:4].hex() == "817e007e"    # 16-bit length
    assert _frame(b"x" * 70000)[:2].hex() == "817f"      # 64-bit length


def test_slash_commands_go_to_the_client_not_the_mud():
    """Typing /js in the browser must fire the handshake, not reach 3K."""
    import mud.web as webmod

    sent, notes = [], []

    class FakeQueue:
        def now(self, line):          # typed input bypasses pacing
            sent.append(("direct", line))

        def put(self, line, priority=0):
            sent.append(("queued", line))

    class FakeSession:
        sec_code, version = 12345, "test"
        mip_seen = False
        codes_seen: dict = {}
        queue = FakeQueue()
        connected, reconnect = True, True

        def send(self, line):
            sent.append(("direct", line))

        def jumpstart(self):
            sent.append(("client", "JUMPSTART"))

    web = webmod.WebServer.__new__(webmod.WebServer)
    web.session = FakeSession()
    web._clients = set()
    web.note = lambda text: notes.append(text)

    web._on_client_message(json.dumps({"t": "cmd", "d": "kill orc"}).encode())
    web._on_client_message(json.dumps({"t": "cmd", "d": "/js"}).encode())
    web._on_client_message(json.dumps({"t": "jumpstart"}).encode())

    assert sent == [
        ("direct", "kill orc"),        # a human typed it -> straight out
        ("client", "JUMPSTART"),
        ("client", "JUMPSTART"),
    ]
    assert all(line != "/js" for _, line in sent)   # never leaks to the MUD
    assert notes and "3klient" in notes[0]


def _armed_session():
    from mud.session import Session

    s = Session("127.0.0.1", 1, sec_code=12345)
    s.jumpstart_retry = 0.0          # no waiting in a test
    outgoing = []
    s.send = lambda line, secret=False: outgoing.append(line)
    return s, outgoing


def test_the_handshake_waits_for_the_login():
    """Announced at the name prompt, "3klient 40142~1.0" is simply typed in as
    somebody's character name."""
    s, outgoing = _armed_session()
    s._on_text(b"Welcome to Three Kingdoms LP-Mud\r\n")
    s._on_text(b"<Entering 3Kingdoms.  Enter your character name>\r\n")
    assert outgoing == [], "spoke while the MUD was asking who we are"
    s._on_text(b"Password: ")
    assert outgoing == [], "spoke while the MUD was asking for a password"


def test_the_handshake_fires_for_someone_who_typed_it_themselves():
    """Read from the text rather than from our own state, so it is just as
    true for somebody who typed their name in at the terminal."""
    s, outgoing = _armed_session()
    s._on_text(b"<Entering 3Kingdoms.  Enter your character name>\r\n")
    s._on_text(b"Password: ")
    assert outgoing == []                       # they are still typing it
    s._on_text(b"\r\nYou have 3 new mails.\r\n")
    assert len(outgoing) == 1 and outgoing[0].startswith("3klient ")


def test_the_handshake_fires_on_a_reconnect():
    """3K answers a reconnect with "welcomes you back from linkdeath", which
    is not the word the old trigger watched for -- so on the common path it
    never fired and the handshake had to be sent by hand."""
    s, outgoing = _armed_session()
    s._on_text(b"<Entering 3Kingdoms.  Enter your character name>\r\nPassword: ")
    s._on_text(b"\r\n3Kingdoms welcomes you back from linkdeath.\r\n")
    assert len(outgoing) == 1 and outgoing[0].startswith("3klient ")


def test_the_handshake_follows_a_login_the_client_did_itself():
    s, outgoing = _armed_session()
    s.login.begin("Player", "hunter2")
    s._on_text(b"<Entering 3Kingdoms.  Enter your character name>")
    s._on_text(b"Password: ")
    assert outgoing[:2] == ["Player", "hunter2"]
    # and the handshake in the same breath: we know the login is answered
    # without having to wait and see what the MUD says about it
    assert outgoing[2].startswith("3klient ")


def test_handshake_retries_until_mip_arrives():
    """The MUD can still be settling when we first ask."""
    s, outgoing = _armed_session()
    s._on_text(b"<Entering 3Kingdoms.  Enter your character name>\r\nPassword: ")
    s._on_text(b"\r\nwelcome back\r\n")
    assert len(outgoing) == 1        # armed and fired

    s._on_text(b"still settling\r\n")
    assert len(outgoing) == 2        # no MIP yet -> announce again

    s.codes_seen["FFF"] += 1
    s.mip_seen = True
    s._on_text(b"more text\r\n")
    assert len(outgoing) == 2        # MIP flowing -> stop announcing


def test_snapshot_carries_recent_chat_history():
    """A browser refresh should not lose the channel history."""
    from mud.session import Session
    from mud.web import WebServer

    session = Session("127.0.0.1", 1, sec_code=12345)
    web = WebServer.__new__(WebServer)
    web.session = session
    web._clients = set()

    session.world.apply("CAA", "ctell~Clan Sa~Friend~[Clan] Friend : moo")
    session.world.apply("BAB", "~Buddy~you around?")
    session.world.apply("BAB", "x~Buddy~yep")

    msgs = web.snapshot()["messages"]
    assert [m["channel"] for m in msgs] == ["Clan Sa", "tell", "tell"]
    assert [m["who"] for m in msgs] == ["Friend", "Buddy", "Buddy"]
    assert [m["mine"] for m in msgs] == [False, False, True]
    assert all("at" in m for m in msgs)          # ordering needs timestamps

    # The monitor prints the MUD's own line and offers the channel command as
    # a reply prefix, so both have to survive the snapshot: "Clan Sa" is for
    # reading, "ctell" is what you type.
    assert msgs[0]["text"] == "[Clan] Friend : moo"
    assert msgs[0]["command"] == "ctell"


def test_the_map_is_not_resent_while_it_has_not_changed():
    """Building it is a query per room and the snapshot goes out several times
    a second.  What is drawn changes only when you move."""
    from mud.session import Session
    from mud.store import Store
    from mud.web import WebServer

    store = Store()
    session = Session("127.0.0.1", 1, sec_code=12345, store=store)
    web = WebServer.__new__(WebServer)
    web.session = session
    web.scripts = None
    web._clients = set()
    web._map_centre = None

    session.mapper.arrived(["n", "e"], ["sky"], at=0.0)

    first = web._map_state()
    assert "rooms" in first and not first.get("unchanged")

    again = web._map_state()
    assert again.get("unchanged") is True
    assert "rooms" not in again              # the browser keeps what it has

    session.mapper.sent("n", at=1.0)
    session.mapper.arrived(["s"], ["road"], at=1.1)
    moved = web._map_state()
    assert "rooms" in moved and not moved.get("unchanged")


def test_the_browser_hears_about_a_route_moving_not_just_starting():
    """The sidebar says which step of how many, and a step counter that only
    moves when a route starts or stops is not a step counter."""
    from mud.web import WebServer

    class Bot:
        def __init__(self):
            self.name, self.steps, self.kills, self.note = "angels2", 0, 0, ""

    class Bots:
        def __init__(self, bot):
            self.running = [bot]

    class Scripts:
        def __init__(self, bot):
            self.routes, self.bots = object(), Bots(bot)

    bot = Bot()
    web = WebServer(object(), scripts=Scripts(bot))
    assert web._routes_changed() is True          # it started
    assert web._routes_changed() is False         # nothing since
    bot.steps += 1
    assert web._routes_changed() is True, "a step went unreported"
    bot.kills += 1
    assert web._routes_changed() is True, "a kill went unreported"


# --- binding the UI -----------------------------------------------------------

def test_a_port_somebody_else_has_is_stepped_over():
    """The first thing that happened on Windows: something already had 8080,
    and "only one usage of each socket address is normally permitted" came out
    as a traceback in front of somebody who had double-clicked an icon."""
    async def scenario():
        async def squatter(reader, writer):
            pass

        blocker = await asyncio.start_server(squatter, "127.0.0.1", 0)
        taken = blocker.sockets[0].getsockname()[1]
        session = Session("127.0.0.1", 1, sec_code=1)
        try:
            web = WebServer(session, port=taken)
            got = await web.start(20)
            await web.stop()
            return taken, got
        finally:
            blocker.close()

    taken, got = asyncio.run(scenario())
    assert got != taken and got > 0


def test_a_port_that_was_asked_for_by_name_is_not_moved():
    """Nobody types a port number and means "or whatever". A silent move is a
    client answering on an address the person is not looking at."""
    async def scenario():
        async def squatter(reader, writer):
            pass

        blocker = await asyncio.start_server(squatter, "127.0.0.1", 0)
        taken = blocker.sockets[0].getsockname()[1]
        session = Session("127.0.0.1", 1, sec_code=1)
        try:
            await WebServer(session, port=taken).start(0)
        except OSError:
            return True
        finally:
            blocker.close()
        return False

    assert asyncio.run(scenario()), "it should have refused"
