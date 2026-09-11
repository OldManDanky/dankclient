"""Sounds for things that happen, and your own files for them.

Each event plays the built-in sound, nothing, or a file you uploaded.  The
files are kept with the map, served back from /sounds/<event>, and the page
is told to play one when a bot ends by itself, when the deadman trips, and
when the MUD drops you.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import events  # noqa: E402
from mud.patrol import Bots, Stopped  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.sounds import MOST, Sounds  # noqa: E402
from mud.web import WebServer  # noqa: E402

MP3 = b"ID3\x03\x00fake mp3 bytes"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def listing(sounds):
    return {s["slot"]: s for s in sounds.listing()}


# --- the store ------------------------------------------------------------------

def test_every_event_starts_with_its_built_in_sound():
    sounds = Sounds(tempfile.mkdtemp())
    got = listing(sounds)
    assert list(got) == ["tell", "channel", "bell", "bot", "idle", "disconnect"]
    assert all(s["choice"] == "builtin" and not s["name"] for s in got.values())


def test_an_upload_is_kept_by_its_event_and_played_from_then_on():
    folder = Path(tempfile.mkdtemp())
    sounds = Sounds(folder)
    assert sounds.upload("bot", "C:\\fakepath\\Horn.MP3", b64(MP3)) is None
    got = listing(sounds)["bot"]
    assert got["choice"] == "file" and got["name"] == "Horn.MP3" and got["stamp"]
    assert (folder / "bot.mp3").read_bytes() == MP3
    again = Sounds(folder)
    assert listing(again)["bot"]["choice"] == "file", "kept across a restart"


def test_a_new_file_of_another_kind_replaces_the_old_one():
    folder = Path(tempfile.mkdtemp())
    sounds = Sounds(folder)
    sounds.upload("tell", "a.mp3", b64(MP3))
    sounds.upload("tell", "b.wav", b64(b"RIFF...."))
    assert sorted(p.name for p in folder.glob("tell.*")) == ["tell.wav"]
    assert listing(sounds)["tell"]["name"] == "b.wav"


def test_what_an_upload_refuses():
    sounds = Sounds(tempfile.mkdtemp())
    assert "not a sound file" in sounds.upload("tell", "notes.txt", b64(b"hi"))
    assert "no such sound" in sounds.upload("../../evil", "x.mp3", b64(MP3))
    assert "did not arrive whole" in sounds.upload("tell", "x.mp3", "@@not base64@@")
    assert "empty" in sounds.upload("tell", "x.mp3", "")
    assert "the most is 2 MB" in sounds.upload("tell", "x.mp3", b64(b"\0" * (MOST + 1)))
    assert all(s["choice"] == "builtin" for s in sounds.listing())


def test_choosing_and_removing():
    folder = Path(tempfile.mkdtemp())
    sounds = Sounds(folder)
    assert "upload a file" in sounds.choose("idle", "file")
    assert sounds.choose("idle", "none") is None
    assert listing(sounds)["idle"]["choice"] == "none"
    sounds.upload("idle", "yawn.ogg", b64(MP3))
    sounds.choose("idle", "builtin")
    assert listing(sounds)["idle"]["name"] == "yawn.ogg", "the file is still there to go back to"
    sounds.remove("idle")
    assert not (folder / "idle.ogg").exists()
    assert listing(sounds)["idle"] == {**listing(sounds)["idle"], "choice": "builtin", "name": ""}


def test_a_file_that_has_gone_falls_back_to_built_in():
    folder = Path(tempfile.mkdtemp())
    sounds = Sounds(folder)
    sounds.upload("bell", "ding.wav", b64(MP3))
    (folder / "bell.wav").unlink()
    assert listing(sounds)["bell"]["choice"] == "builtin"


# --- the page's side -----------------------------------------------------------

def web_with_sounds():
    session = Session("127.0.0.1", 1, sec_code=12345)
    web = WebServer(session, sounds=Sounds(tempfile.mkdtemp()))
    pushed = []
    web.push = pushed.append
    return session, web, pushed


def test_the_page_uploads_chooses_and_hears_back():
    session, web, pushed = web_with_sounds()
    msg = {"t": "sound", "op": "upload", "slot": "bot", "name": "horn.mp3", "data": b64(MP3)}
    web._on_client_message(json.dumps(msg).encode())
    assert pushed[-1]["t"] == "sounds" and pushed[-1]["error"] == ""
    assert {s["slot"]: s["choice"] for s in pushed[-1]["slots"]}["bot"] == "file"
    web._on_client_message(b'{"t": "sound", "op": "upload", "slot": "bot", "name": "x.txt", "data": "aGk="}')
    assert "not a sound file" in pushed[-1]["error"]
    assert web.greeting()["sounds"] == web.sounds.listing(), "a page that opens is told"


def test_the_file_is_served_back_and_nothing_else_is():
    async def go():
        session = Session("127.0.0.1", 1, sec_code=12345)
        sounds = Sounds(tempfile.mkdtemp())
        sounds.upload("bot", "horn.mp3", b64(MP3))
        web = WebServer(session, port=0, sounds=sounds)
        port = await web.start()

        def fetch(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                    return r.status, r.headers.get("Content-Type"), r.read()
            except urllib.error.HTTPError as err:
                return err.code, None, b""

        got = await asyncio.to_thread(fetch, "/sounds/bot?v=123")
        assert got == (200, "audio/mpeg", MP3), got[:2]
        for path in ("/sounds/tell", "/sounds/../sounds.json", "/sounds/sounds.json",
                     "/sounds/..%2Fsounds.json"):
            assert (await asyncio.to_thread(fetch, path))[0] == 404, path
        await web.stop() if hasattr(web, "stop") else None
    asyncio.run(go())


def test_the_page_is_told_to_play_when_the_deadman_trips_or_the_mud_drops_you():
    session, web, pushed = web_with_sounds()
    web._wire_session()
    session.bus.emit(events.STATE, "deadman", True, False)
    session.bus.emit(events.STATE, "deadman", False, True)
    assert [m for m in pushed if m.get("t") == "play"] == [{"t": "play", "slot": "idle"}]
    session.wanted = True
    session.bus.emit(events.DISCONNECTED)
    session.wanted = False                         # Disconnect, pressed
    session.bus.emit(events.DISCONNECTED)
    assert [m["slot"] for m in pushed if m.get("t") == "play"] == ["idle", "disconnect"]


def test_a_bot_that_ends_by_itself_plays_and_one_stopped_does_not():
    async def go():
        session, web, pushed = web_with_sounds()
        web._wire_session()
        bots = Bots(session)
        plays = lambda: [m["slot"] for m in pushed if m.get("t") == "play"]  # noqa: E731

        async def done():
            return None

        async def gives_up():
            raise Stopped("could not see the room")

        async def forever():
            await asyncio.sleep(60)

        bots.start("hunt", done, owner="route:a1")
        await asyncio.sleep(0.01)
        assert plays() == ["bot"], "finished"
        bots.start("hunt", gives_up, owner="route:a1")
        await asyncio.sleep(0.01)
        assert plays() == ["bot", "bot"], "gave up"
        bots.start("hunt", forever, owner="route:a1")
        await asyncio.sleep(0.01)
        bots.stop("hunt")
        await asyncio.sleep(0.01)
        assert plays() == ["bot", "bot"], "Stop is not a reason to chime"
        bots.start("speedwalk", done, owner="client")
        await asyncio.sleep(0.01)
        assert plays() == ["bot", "bot"], "nor is arriving somewhere on the map"
    asyncio.run(go())
