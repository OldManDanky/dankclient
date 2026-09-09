"""The capture is the mapper's and the debugger's input, so what it records
has to survive a round trip exactly."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.capture import (  # noqa: E402
    CaptureWriter,
    read_capture,
    read_commands,
    replay,
)


def _writer(tmp):
    return CaptureWriter(Path(tmp) / "run")


def test_the_stream_and_the_commands_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write(b"#K%12345003DDDn~e")
        w.sent("n")
        w.write(b"\r\nYou walk north.\r\n")
        w.close()

        stem = Path(tmp) / "run"
        assert b"".join(c for _, c in read_capture(stem)) == (
            b"#K%12345003DDDn~e\r\nYou walk north.\r\n"
        )
        assert [line for _, line in read_commands(stem)] == ["n"]


def test_our_bytes_stay_out_of_the_mud_stream():
    """The .bin has to replay through the scanner verbatim.  Splicing what we
    sent into it would put our own text where MIP frames are expected."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.sent("climb pipe")
        w.write(b"hello")
        w.close()
        assert (Path(tmp) / "run.bin").read_bytes() == b"hello"


def test_a_command_carrying_a_newline_stays_one_record():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.sent("say a\nb\tc\\d")
        w.close()
        assert [line for _, line in read_commands(Path(tmp) / "run")] == [
            "say a\nb\tc\\d"
        ]


def test_replay_puts_a_command_before_the_reply_it_caused():
    """The mapper reads a move as 'we sent something, then a room block came
    back'.  If a same-instant reply sorted first the move would be lost."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.sent("n")
        w.write(b"room")
        w.close()
        kinds = [(kind, payload) for kind, _, payload in replay(Path(tmp) / "run")]
        assert kinds == [("sent", "n"), ("recv", b"room")]


def test_an_old_capture_with_no_commands_still_replays():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write(b"hello")
        w.close()
        (Path(tmp) / "run.out").unlink()
        stem = Path(tmp) / "run"
        assert list(read_commands(stem)) == []
        assert [p for _, _, p in replay(stem)] == [b"hello"]


def test_captures_are_never_overwritten():
    with tempfile.TemporaryDirectory() as tmp:
        first = _writer(tmp)
        first.write(b"irreplaceable")
        first.close()
        second = _writer(tmp)
        second.close()
        assert second.bin_path.name == "run-1.bin"
        assert (Path(tmp) / "run.bin").read_bytes() == b"irreplaceable"


def test_every_outbound_line_reaches_the_log():
    """Scripts, the queue, the browser and the jumpstart all funnel through
    Session.send, so logging there is what makes the record complete."""
    from mud.session import Session

    class FakeWriter:
        def __init__(self):
            self.wrote = bytearray()

        def write(self, data):
            self.wrote += data

    with tempfile.TemporaryDirectory() as tmp:
        log = _writer(tmp)
        session = Session("127.0.0.1", 1, sec_code=12345, raw_log=log)
        session._writer = FakeWriter()

        session.jumpstart()
        session.send("climb pipe")
        log.close()

        sent = [line for _, line in read_commands(Path(tmp) / "run")]
        assert sent == ["3klient 12345~" + session.version, "climb pipe"]
