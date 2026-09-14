"""A line that starts with `\\` goes to 3K exactly as typed.

TinTin++'s escape: `\\tell buddy n;w;s;e` is one tell, not a tell and three
steps.  Not split on `;`, not an alias, not a client command; the one
backslash comes off.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.commands import stack, verbatim  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


class Wire:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        pass


def test_the_whole_line_is_one_command_with_the_backslash_off():
    assert stack(r"\tell buddy n;w;s;e;s;s;w;") == [r"\tell buddy n;w;s;e;s;s;w;"]
    assert verbatim(r"\tell buddy n;w;s;e;s;s;w;") == "tell buddy n;w;s;e;s;s;w;"
    assert verbatim("\\\\o/") == "\\o/", "two backslashes send one"
    assert verbatim("tell buddy hi") is None
    assert stack("n;w") == ["n", "w"], "without it, a line is split as ever"


def test_typed_on_the_page_it_skips_splitting_aliases_and_client_commands():
    folder = Path(tempfile.mkdtemp())
    try:
        s = Session(jumpstart=False, prefixes_path=str(folder / "p.json"))
        wire = Wire()
        s._writer, s.connected = wire, True
        host = ScriptHost(s, folder)
        store = RuleStore(host, folder / "rules.json")
        host.rules = store
        _, err = store.upsert({"kind": "alias", "pattern": "hi", "mode": "contains",
                               "actions": [{"type": "send", "text": "say hello"}]})
        assert err is None
        web = WebServer(s, scripts=host)
        said: list[str] = []
        web.note = said.append

        def typed(line: str) -> list[str]:
            wire.sent.clear()
            web._on_client_message(('{"t": "cmd", "d": %s}' % _json(line)).encode())
            return [b.decode().strip() for b in wire.sent]

        assert typed(r"\tell buddy n;w;s;e") == ["tell buddy n;w;s;e"]
        assert typed("hi there") == ["say hello"], "the alias, without it"
        assert typed(r"\hi there") == ["hi there"], "not the alias, with it"
        assert typed(r"\/js") == ["/js"] and not said, "not a client command either"
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _json(text: str) -> str:
    import json
    return json.dumps(text)
