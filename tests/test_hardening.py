"""The edges: a connection that dies without a word, a page that stops
reading, a message that is not what it says it is, a file half written when
the power went.

Every one of these was reproduced against the client before it was fixed.  The
escape out of the extraction folder wrote a real file; half a rules.json
became two bytes on the next save; three malformed messages each closed the
socket every panel talks down.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import os
import socket
import stat
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events, update  # noqa: E402
from mud import web as webmod  # noqa: E402
from mud.botstore import RouteStore  # noqa: E402
from mud.paths import write_atomically  # noqa: E402
from mud.prefixes import Prefixes  # noqa: E402
from mud.profile import Character, Characters  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.telnet import IAC, SB, SB_MOST, SE, TelnetFilter  # noqa: E402
from mud.web import (WebServer, _read_frame, loopback_host,  # noqa: E402
                     web_address)

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def session(host: str = "127.0.0.1", port: int = 9) -> Session:
    # Never the default prefixes path: it is relative, and a test run from a
    # checkout would otherwise be reading -- and setting aside -- a real one.
    return Session(host, port, sec_code=12345,
                   prefixes_path=str(tmp() / "prefixes.json"))


class Wire:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        pass


def online(s: Session) -> Wire:
    s._writer = Wire()
    s.connected = True
    return s._writer


# --- what goes to the MUD ----------------------------------------------------

def test_a_line_break_cannot_become_a_second_command():
    """A rule that puts a tell into what it sends would otherwise let another
    player add a command of their own to it."""
    s = session()
    wire = online(s)
    s.send("tell Friend hi\ngive all to Someone")
    s.send("say one\r\ntwo\rthree")
    assert wire.sent == [b"tell Friend hi give all to Someone\r\n",
                         b"say one two three\r\n"]


def test_a_literal_0xff_is_escaped_for_telnet():
    s = session()
    wire = online(s)
    s.send("say \xff")
    assert wire.sent == [b"say \xff\xff\r\n"]


def test_a_pasted_block_goes_out_one_command_at_a_time():
    s = session()
    wire = online(s)
    web = WebServer(s)
    web._on_client_message(json.dumps({"t": "cmd", "d": "n\ne\r\ns"}).encode())
    assert wire.sent == [b"n\r\n", b"e\r\n", b"s\r\n"]


# --- the MUD connection ------------------------------------------------------

def test_the_mud_socket_notices_a_link_that_died_silently():
    async def go():
        srv = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        s = session("127.0.0.1", srv.sockets[0].getsockname()[1])
        await s.connect()
        sock = s._writer.get_extra_info("socket")
        on = sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
        idle = (sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE)
                if hasattr(socket, "TCP_KEEPIDLE") else 30)
        await s.aclose()
        srv.close()
        return on, idle

    on, idle = asyncio.run(go())
    assert on, "keepalive is off: a dead link waits for ever"
    assert idle == 30, "the system default is two hours"


def test_a_connect_that_is_never_answered_gives_up():
    """Packets dropped rather than refused wait on the operating system -- two
    minutes on Linux -- and Disconnect cannot interrupt it meanwhile."""
    async def go():
        async def never(*_a, **_k):
            await asyncio.sleep(3600)

        was = asyncio.open_connection
        asyncio.open_connection = never
        try:
            s = session()
            s.connect_timeout = 0.2
            started = time.monotonic()
            try:
                await s.connect()
            except OSError as exc:        # what _come_back retries on
                return type(exc), time.monotonic() - started
            return None, 0.0
        finally:
            asyncio.open_connection = was

    kind, took = asyncio.run(go())
    assert kind is TimeoutError and took < 2


def test_something_the_mud_sent_that_cannot_be_handled_costs_one_chunk():
    """The read loop is what everything hangs off.  An exception in it used to
    end the session; with a window open, silently."""
    async def go():
        async def mud(reader, writer):
            writer.write(b"first\r\n")
            await writer.drain()
            await asyncio.sleep(0.1)
            writer.write(b"second\r\n")
            await writer.drain()
            await asyncio.sleep(0.1)
            writer.close()

        srv = await asyncio.start_server(mud, "127.0.0.1", 0)
        s = session("127.0.0.1", srv.sockets[0].getsockname()[1])
        seen: list[bytes] = []

        def picky(data: bytes) -> None:
            seen.append(data)
            if b"first" in data:
                raise ValueError("a hook the bus is not protecting")

        s.on_text.append(picky)
        await s.connect()
        with contextlib.redirect_stderr(io.StringIO()):
            await asyncio.wait_for(s.run(), 5)
        srv.close()
        return b"".join(seen)

    assert b"second" in asyncio.run(go())


def test_a_subnegotiation_that_never_ends_does_not_grow_for_ever():
    f = TelnetFilter()
    f.feed(bytes([IAC, SB, 24]) + b"x" * (SB_MOST * 10))
    assert len(f._sub) <= SB_MOST
    clean, _reply, marks = f.feed(bytes([IAC, SE]) + b"hello")
    assert clean == b"hello" and marks == ["sb:24"]


# --- the page's socket -------------------------------------------------------

def frame(obj, *, final: bool = True, opcode: int = 0x1,
          masked: bool = True) -> bytes:
    body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    n = len(body)
    head = bytearray([(0x80 if final else 0) | opcode])
    bit = 0x80 if masked else 0
    if n < 126:
        head.append(bit | n)
    elif n < 65536:
        head += bytes([bit | 126]) + n.to_bytes(2, "big")
    else:
        head += bytes([bit | 127]) + n.to_bytes(8, "big")
    return bytes(head) + (b"\0\0\0\0" if masked else b"") + body


async def served():
    web = WebServer(session(), port=0)
    return web, await web.start()


async def socket_to(port: int, host: str = "127.0.0.1"):
    r, w = await asyncio.open_connection("127.0.0.1", port)
    key = base64.b64encode(os.urandom(16)).decode()
    w.write(f"GET /ws HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n\r\n".encode())
    await w.drain()
    return r, w, await r.readuntil(b"\r\n\r\n")


async def heard_help(r) -> bool:
    """Wait for the command list; False if the socket closes first."""
    try:
        while True:
            op, payload = await asyncio.wait_for(_read_frame(r), 2)
            if op == 0x8:
                return False
            if op == 0x1 and json.loads(payload).get("t") == "help":
                return True
    except (asyncio.TimeoutError, asyncio.IncompleteReadError):
        return False


async def close_code(r) -> int:
    while True:
        op, payload = await asyncio.wait_for(_read_frame(r), 2)
        if op == 0x8:
            return int.from_bytes(payload[:2], "big")


def quietly(coro):
    with contextlib.redirect_stderr(io.StringIO()):
        return asyncio.run(coro)


def test_a_message_that_cannot_be_handled_does_not_close_the_socket():
    async def go():
        web, port = await served()
        r, w, _ = await socket_to(port)
        for bad in (b"[]", b"null", b"{not json", {"t": "cmd", "d": 5}):
            w.write(frame(bad))

        def broken(_text):
            raise RuntimeError("a handler with a bug in it")

        web._command = broken
        w.write(frame({"t": "cmd", "d": "look"}))
        await w.drain()
        ok = await heard_help_after(r, w)
        await web.stop()
        return ok

    async def heard_help_after(r, w):
        w.write(frame({"t": "help"}))
        await w.drain()
        return await heard_help(r)

    assert quietly(go()), "one bad message closed every panel's socket"


def test_a_frame_claiming_to_be_enormous_is_refused_not_waited_for():
    async def go():
        web, port = await served()
        r, w, _ = await socket_to(port)
        w.write(bytes([0x81, 0x80 | 127]) + (1 << 62).to_bytes(8, "big"))
        await w.drain()
        code = await close_code(r)
        await web.stop()
        return code

    assert quietly(go()) == 1009


def test_a_frame_the_page_did_not_mask_is_refused():
    async def go():
        web, port = await served()
        r, w, _ = await socket_to(port)
        w.write(frame({"t": "help"}, masked=False))
        await w.drain()
        code = await close_code(r)
        await web.stop()
        return code

    assert quietly(go()) == 1002


def test_a_message_in_pieces_is_put_back_together():
    async def go():
        web, port = await served()
        r, w, _ = await socket_to(port)
        body = json.dumps({"t": "help"}).encode()
        w.write(frame(body[:4], final=False) + frame(body[4:], opcode=0x0))
        await w.drain()
        ok = await heard_help(r)
        await web.stop()
        return ok

    assert quietly(go())


def test_a_page_that_stops_reading_is_let_go():
    """It reconnects by itself and is sent the scrollback.  Held, it had
    everything the MUD said queued for it without limit."""
    async def go():
        web, port = await served()
        r, w, _ = await socket_to(port)
        await asyncio.sleep(0.1)
        assert len(web._clients) == 1
        for i in range(20000):
            web.push({"t": "text", "d": "x" * 1000})
            if i % 1000 == 0:
                await asyncio.sleep(0)
        left = len(web._clients)
        await web.stop()
        return left

    assert quietly(go()) == 0


def test_a_connection_that_never_says_anything_is_closed():
    async def go():
        was, webmod.HEADERS_WITHIN = webmod.HEADERS_WITHIN, 0.3
        try:
            web, port = await served()
            r, _w = await asyncio.open_connection("127.0.0.1", port)
            got = await asyncio.wait_for(r.read(1), 3)
            await web.stop()
            return got
        finally:
            webmod.HEADERS_WITHIN = was

    assert quietly(go()) == b""


def test_a_header_longer_than_any_browser_sends_is_closed_quietly():
    async def go():
        web, port = await served()
        loop = asyncio.get_running_loop()
        escaped: list = []
        loop.set_exception_handler(lambda _l, ctx: escaped.append(ctx))
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(b"GET / HTTP/1.1\r\nX: " + b"a" * 70000 + b"\r\n\r\n")
        await w.drain()
        got = await asyncio.wait_for(r.read(), 3)
        await web.stop()
        return escaped, got

    escaped, got = quietly(go())
    assert not escaped, escaped
    assert got == b""


def test_another_domain_pointed_at_this_machine_is_refused():
    """DNS rebinding.  The page is same-origin with itself, but its requests
    still carry its own name."""
    async def go():
        web, port = await served()
        _r, _w, head = await socket_to(port, host="evil.example:8080")
        r, w = await asyncio.open_connection("127.0.0.1", port)
        w.write(b"GET / HTTP/1.1\r\nHost: evil.example\r\n\r\n")
        await w.drain()
        page = await asyncio.wait_for(r.read(), 3)
        await web.stop()
        return head, page

    head, page = quietly(go())
    assert head.startswith(b"HTTP/1.1 403")
    assert page.startswith(b"HTTP/1.1 403")


def test_the_ui_answers_only_to_this_machines_names():
    for ok in ("127.0.0.1:8080", "localhost:8081", "[::1]:8080", "LOCALHOST", ""):
        assert loopback_host(ok), ok
    for bad in ("evil.example", "evil.example:8080", "127.0.0.1.evil.example",
                "[::1"):
        assert not loopback_host(bad), bad


# --- links in the output -----------------------------------------------------

def test_only_web_addresses_are_handed_to_the_browser():
    for good in ("http://3k.org", "https://github.com/OldManDanky/dankclient",
                 "https://example.com/a?b=c#d"):
        assert web_address(good) == good
    for bad in ("javascript:alert(1)", "file:///C:/Windows/System32/calc.exe",
                "C:\\Windows\\calc.exe", "\\\\host\\share", "ms-settings:",
                "https://", "http://a b", 'https://x.com/"&calc',
                "https://x.com/\ncalc", "https://" + "a" * 3000, 5, None):
        assert web_address(bad) is None, bad


def test_an_address_is_opened_only_if_it_is_a_web_address():
    async def go():
        opened: list[str] = []
        was = webmod.webbrowser.open
        webmod.webbrowser.open = lambda url: opened.append(url) or True
        try:
            web = WebServer(session())
            for url in ("https://3k.org/", "file:///C:/x", "javascript:x"):
                web._on_client_message(
                    json.dumps({"t": "open", "url": url}).encode())
            await asyncio.sleep(0.2)
        finally:
            webmod.webbrowser.open = was
        return opened

    assert asyncio.run(go()) == ["https://3k.org/"]


def test_links_open_on_shift_click_and_through_the_server():
    js = (UI / "app.js").read_text()
    assert "registerLinkProvider" in js
    assert "event.shiftKey" in js, "a plain click is for selecting text"
    assert "t: 'open'" in js
    assert "window.open(" not in js, "that opens inside the app's own profile"


def test_ctrl_c_copies_the_terminal_selection():
    js = (UI / "app.js").read_text()
    assert "term.hasSelection()" in js and "term.getSelection()" in js
    assert "selectionBackground" in js


def test_the_release_link_is_checked_in_the_page_too():
    assert "startsWith('https://github.com/')" in (UI / "about.js").read_text()


# --- files on disk -----------------------------------------------------------

RULE = {"kind": "trigger", "pattern": "p", "actions": [{"type": "send", "text": "y"}]}


def test_a_setting_from_a_newer_version_does_not_stop_this_one_starting():
    d = tmp()
    (d / "rules.json").write_text(json.dumps(
        [dict(RULE, added_later=True),
         dict(RULE, pattern="q", actions="not a list of actions")]))
    rules = RuleStore(None, d / "rules.json")
    rules.load()
    assert [r.pattern for r in rules.rules] == ["p"]

    (d / "routes.json").write_text(json.dumps(
        [{"name": "r", "path": "n e", "added_later": 1},
         {"name": "broken", "path": 5}]))
    routes = RouteStore(None, d / "routes.json")
    routes.load()
    assert [r.name for r in routes.routes] == ["r"]


def half(text: str) -> str:
    return text[: len(text) // 2]


def test_a_half_written_file_is_kept_rather_than_saved_over():
    """It used to load as empty, and the next save wrote the emptiness back."""
    d = tmp()
    whole = json.dumps([dict(RULE, pattern=f"p{i}") for i in range(50)])
    cases = {
        "rules.json": (whole, lambda p: RuleStore(None, p)),
        "routes.json": (json.dumps([{"name": f"r{i}", "path": "n"}
                                    for i in range(50)]),
                        lambda p: RouteStore(None, p)),
        "characters.json": (json.dumps([{"name": f"c{i}"} for i in range(50)]),
                            None),
        "prefixes.json": (json.dumps({"verb": "aset", "set": [["a", "b"]] * 50}),
                          None),
    }
    with contextlib.redirect_stderr(io.StringIO()):
        for name, (text, make) in cases.items():
            path = d / name
            path.write_text(half(text))
            if name == "characters.json":
                chars = Characters(d, d / "seed")
                chars.put(Character("newcomer"))
            elif name == "prefixes.json":
                Prefixes(path).save()
            else:
                store = make(path)
                store.load()
                store.save()
            kept = [p for p in d.iterdir()
                    if p.name.startswith(name + ".unreadable-")]
            assert kept and kept[0].read_text() == half(text), name
            json.loads(path.read_text())     # and what replaced it is whole
    assert not [p for p in d.iterdir() if p.name.endswith(".tmp")]


def test_a_save_that_fails_leaves_the_old_file_alone():
    d = tmp()
    path = d / "rules.json"
    path.write_text("the old rules")
    was = os.replace

    def refuse(*_a):
        raise OSError("the disk is full")

    os.replace = refuse
    try:
        write_atomically(path, "the new rules")
    except OSError:
        pass
    finally:
        os.replace = was
    assert path.read_text() == "the old rules"
    assert [p.name for p in d.iterdir()] == ["rules.json"]


def test_the_character_list_is_still_private():
    if os.name != "posix":
        return
    d = tmp()
    Characters(d, d / "seed").put(Character("someone", password="secret"))
    assert stat.S_IMODE((d / "characters.json").stat().st_mode) == 0o600


# --- background work ---------------------------------------------------------

def test_a_background_task_that_fails_says_so():
    """Three times, a panel sat on "working" because the task behind it had
    raised and nothing anywhere said."""
    async def go():
        async def broken():
            raise ValueError("nobody would have known")

        task = events.spawn(broken(), "a test task")
        held = task in events._running
        await asyncio.sleep(0.05)
        return held, task in events._running

    said = io.StringIO()
    with contextlib.redirect_stderr(said):
        held, still = asyncio.run(go())
    assert held and not still
    assert "a test task failed" in said.getvalue()
    assert "nobody would have known" in said.getvalue()


# --- somebody else's tarball -------------------------------------------------

def tarball(names: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, body in names.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


def test_a_folder_whose_name_starts_the_same_is_still_outside():
    """Unpacking into `out`, the path `out2/f` starts with `out` -- which is
    all the old check asked."""
    base = tmp()
    update._unpack(tarball({
        "3kdb-master/common/bot/../../../out2/planted": b"x"}), base / "out")
    assert not (base / "out2").exists()


def test_names_that_mean_something_else_on_windows_are_refused():
    base = tmp()
    into = base / "out"
    update._unpack(tarball({
        "3kdb-master/common/bot/..\\..\\..\\evil": b"x",
        "3kdb-master/common/bot/C:evil": b"x",
        "3kdb-master/common/bot/fine.bot": b"ok",
    }), into)
    files = sorted(p.relative_to(base).as_posix()
                   for p in base.rglob("*") if p.is_file())
    assert files == ["out/common/bot/fine.bot"]


def test_an_archive_that_unpacks_into_too_much_is_refused():
    was, update.MOST_UNPACKED = update.MOST_UNPACKED, 10
    try:
        update._unpack(tarball({"3kdb-master/common/bot/a": b"x" * 20}),
                       tmp() / "out")
    except ValueError:
        return
    finally:
        update.MOST_UNPACKED = was
    raise AssertionError("unpacked past the limit")


def test_the_release_link_is_only_ever_a_github_page():
    body = {"tag_name": "v9.0.0", "html_url": "javascript:alert(1)",
            "assets": [{"name": "x.msi",
                        "browser_download_url": "https://evil.example/x.msi"}]}
    was, update._get = update._get, lambda url, timeout: json.dumps(body).encode()
    try:
        got = update.newer_release(have="0.1.0")
    finally:
        update._get = was
    assert got["newer"] and got["url"] == "" and got["page"] == ""
