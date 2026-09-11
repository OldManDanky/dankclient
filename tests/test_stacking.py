"""Stacked commands: `n;w;n;n;e;n` typed once is six commands, in order.

Each piece goes where a typed line would -- an alias, a client command, or
3K.  A line that starts with `/` is the client's and keeps its own `;`
(`/alias gk kill {1};glance`), and `\\;` is a semicolon that stays put.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.commands import stack  # noqa: E402
from mud.rules import RuleStore  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402
from mud.web import WebServer  # noqa: E402


def test_a_line_is_split_on_semicolons():
    assert stack("n;w;n;n;e;n") == ["n", "w", "n", "n", "e", "n"]
    assert stack("kill rat ; get all") == ["kill rat", "get all"]
    assert stack("n;;w;") == ["n", "w"], "empty pieces are nothing"


def test_what_is_left_alone():
    assert stack("  say  hi  ") == ["  say  hi  "], "no ; -- not touched at all"
    assert stack("") == [""], "Enter on nothing still asks 3K for a prompt"
    assert stack("/alias gk kill {1};glance") == ["/alias gk kill {1};glance"]
    assert stack(r"say hi\; bye;n") == ["say hi; bye", "n"]


def web_with(tmp):
    session = Session("127.0.0.1", 1, sec_code=12345)
    sent = []
    session.queue.now = sent.append
    host = ScriptHost(session, tmp)
    host.rules = RuleStore(host, Path(tmp) / "rules.json")
    web = WebServer(session, scripts=host)
    web._is_up = lambda: True
    web.note = lambda text: sent.append(f"[note] {text}")
    return web, host, sent


def test_the_input_box_sends_each_in_order():
    with tempfile.TemporaryDirectory() as tmp:
        web, host, sent = web_with(tmp)
        web._on_client_message(b'{"t": "cmd", "d": "n;w;n;n;e;n"}')
        assert sent == ["n", "w", "n", "n", "e", "n"]


def test_each_piece_meets_the_aliases_and_the_client_commands():
    with tempfile.TemporaryDirectory() as tmp:
        web, host, sent = web_with(tmp)
        host.rules.upsert({"kind": "alias", "mode": "command", "pattern": "gk",
                           "actions": [{"type": "send", "text": "kill {1}"}]})
        web._on_client_message(b'{"t": "cmd", "d": "n;gk rat;/groups;s"}')
        assert sent[0] == "n"
        assert "kill rat" in host.session.queue.pending or "kill rat" in sent
        assert any(s.startswith("[note] no groups") for s in sent), sent
        assert sent[-1] == "s"
        assert "/groups" not in sent, "never sent to 3K"


def test_a_client_command_keeps_its_own_semicolons():
    with tempfile.TemporaryDirectory() as tmp:
        web, host, sent = web_with(tmp)
        web._on_client_message(b'{"t": "cmd", "d": "/alias gk kill {1};glance"}')
        rule = host.rules.rules[0]
        assert [a["text"] for a in rule.actions] == ["kill {1}", "glance"]
        assert not [s for s in sent if not s.startswith("[note]")]


def test_the_map_is_told_of_every_step():
    """Typed stacks go out the way /go's do, so dead reckoning follows."""
    with tempfile.TemporaryDirectory() as tmp:
        from mud.store import Store
        session = Session("127.0.0.1", 1, sec_code=12345, store=Store())
        told = []
        session.mapper.sent = lambda line, at=None: told.append(line)
        session._writer = type("W", (), {"write": lambda self, d: None})()
        web = WebServer(session)
        web._is_up = lambda: True
        web._on_client_message(b'{"t": "cmd", "d": "n;w;e"}')
        assert told == ["n", "w", "e"]
