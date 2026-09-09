"""GUI-managed rules: validation, registration, persistence, code view."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.rules import Rule, RuleStore, _safe_format  # noqa: E402
from mud.scripts import ScriptHost  # noqa: E402
from mud.session import Session  # noqa: E402

TMP = Path("/tmp/mudrules")


def outgoing(session) -> list[str]:
    return session.sent_lines + session.queue.pending


def make():
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    session = Session("127.0.0.1", 1, sec_code=12345)
    session.sent_lines = []
    session.send = session.sent_lines.append
    session.queue._send = session.sent_lines.append
    host = ScriptHost(session, TMP)
    store = RuleStore(host, TMP / "rules.json")
    host.rules = store
    return session, host, store


def test_rule_validation_catches_the_usual_mistakes():
    assert Rule(pattern="", actions=[{"type": "send", "text": "x"}]).validate()
    assert Rule(pattern="x", actions=[]).validate() == "no actions"
    bad = Rule(pattern="(unclosed", mode="regex",
               actions=[{"type": "send", "text": "x"}])
    assert "bad regex" in bad.validate()
    good = Rule(pattern="tells you", actions=[{"type": "send", "text": "hi"}])
    assert good.validate() is None


def test_saving_registers_it_into_the_same_engine_scripts_use():
    session, host, store = make()
    rule, err = store.upsert({
        "kind": "trigger", "pattern": "has arrived", "mode": "contains",
        "actions": [{"type": "send", "text": "greet"}],
    })
    assert err is None
    hits = host.triggers.fire("Grot has arrived")
    assert len(hits) == 1
    hits[0][0].fn(hits[0][1])
    assert outgoing(session) == ["greet"]


def test_captures_substitute_into_actions():
    session, host, store = make()
    store.upsert({
        "kind": "trigger", "mode": "regex",
        "pattern": r"(?P<who>\w+) has arrived",
        "actions": [{"type": "send", "text": "wave {who}"}],
    })
    trig, captured = host.triggers.fire("Grot has arrived")[0]
    trig.fn(captured)
    assert outgoing(session) == ["wave Grot"]


def test_unknown_placeholders_are_left_alone():
    assert _safe_format("wave {who} at {nope}", {"who": "Grot"}) == "wave Grot at {nope}"


def test_disabled_rules_do_not_register():
    session, host, store = make()
    store.upsert({"pattern": "ping", "enabled": False,
                  "actions": [{"type": "send", "text": "pong"}]})
    assert host.triggers.fire("ping") == []


def test_rules_persist_and_reload():
    session, host, store = make()
    store.upsert({"pattern": "ping", "name": "test",
                  "actions": [{"type": "send", "text": "pong"}]})
    assert json.loads((TMP / "rules.json").read_text())[0]["name"] == "test"

    session2, host2, store2 = Session("127.0.0.1", 1), None, None
    host2 = ScriptHost(session2, TMP)
    store2 = RuleStore(host2, TMP / "rules.json")
    store2.load()
    store2.register()
    assert len(store2.rules) == 1
    assert len(host2.triggers.fire("ping")) == 1


def test_deleting_unregisters():
    session, host, store = make()
    rule, _ = store.upsert({"pattern": "ping",
                            "actions": [{"type": "send", "text": "pong"}]})
    assert store.delete(rule.id) is True
    assert host.triggers.fire("ping") == []
    assert store.delete("nope") is False


def test_script_reload_does_not_drop_gui_rules():
    """Reloading a script file clears owners wholesale; GUI rules must survive."""
    session, host, store = make()
    store.upsert({"pattern": "ping", "actions": [{"type": "send", "text": "pong"}]})
    (TMP / "s.py").write_text("@trigger('other')\ndef a(m): pass\n")
    host.reload_changed()
    assert len(host.triggers.fire("ping")) == 1, "GUI rule was lost on reload"


def test_as_python_renders_the_equivalent_script():
    code = Rule(kind="trigger", name="greet arrivals", mode="regex",
                pattern=r"(?P<who>\w+) has arrived",
                actions=[{"type": "send", "text": "wave {who}"}]).as_python()
    assert "@trigger(" in code and "def greet_arrivals(m):" in code
    # captures arrive as the dict `m`, so a bare {who} would be a NameError
    assert "{m['who']}" in code

    ns = {"trigger": lambda *a, **k: (lambda f: f), "send": lambda s: sent.append(s)}
    sent: list[str] = []
    exec(code, ns)                      # the generated script must actually run
    ns["greet_arrivals"]({"who": "Grot"})
    assert sent == ["wave Grot"]


def test_listing_separates_editable_rules_from_script_ones():
    session, host, store = make()
    store.upsert({"pattern": "ping", "actions": [{"type": "log", "text": "x"}]})
    (TMP / "s.py").write_text("@trigger('from a file')\ndef a(m): pass\n")
    host.load(TMP / "s.py")
    listing = store.listing()
    assert len(listing["rules"]) == 1
    assert any(t["pattern"] == "from a file" for t in listing["scripts"])
    assert all(t["owner"] != "gui" for t in listing["scripts"])


def test_rule_pace_reaches_the_queue():
    """A corpse trigger should not wait two seconds for a round."""
    from mud.outbound import NOW, ROUND

    session, host, store = make()
    session.apm.soft = 0                      # budget exhausted

    store.upsert({"pattern": "killing blow", "pace": NOW,
                  "actions": [{"type": "send", "text": "get corpse"}]})
    trig, cap = host.triggers.fire("Player dealt the killing blow to Gabriel.")[0]
    trig.fn(cap)
    assert session.sent_lines == ["get corpse"], "immediate must ignore the budget"

    store.upsert({"pattern": "round start", "pace": ROUND,
                  "actions": [{"type": "send", "text": "bash"}]})
    trig, cap = host.triggers.fire("round start")[0]
    trig.fn(cap)
    assert session.queue.pending == ["bash"]


def test_pace_survives_the_round_trip_and_the_code_view():
    from mud.outbound import NOW
    rule = Rule(pattern="x", pace=NOW,
                actions=[{"type": "send", "text": "get corpse"}])
    assert "pace='now'" in rule.as_python()
    assert Rule(pattern="x", pace="nonsense",
                actions=[{"type": "send", "text": "y"}]).pace == "paced"


def test_alias_with_arguments_end_to_end():
    """`gk orc` -> the actions see orc, which is the whole point."""
    session, host, store = make()
    store.upsert({
        "kind": "alias", "mode": "command", "pattern": "gk", "pace": "now",
        "actions": [{"type": "send", "text": "consider {args}"},
                    {"type": "send", "text": "kill {args}"}],
    })
    assert host.input("gk a big orc") is True
    assert session.sent_lines == ["consider a big orc", "kill a big orc"]

    session.sent_lines.clear()
    assert host.input("gkk orc") is False        # must not fire on a near miss
    assert session.sent_lines == []


# --- MIP event rules ---------------------------------------------------------

def test_event_rule_fires_on_a_tell():
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "tell", "pace": "now",
        "actions": [{"type": "send", "text": "tell {who} omw"}],
    })
    session.world.apply("BAB", "~Friend~do you need an xmute?")
    assert session.sent_lines == ["tell Friend omw"]


def test_event_conditions_filter():
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "chat", "pace": "now",
        "conditions": [{"field": "channel", "op": "eq", "value": "Clan Sa"}],
        "actions": [{"type": "send", "text": "ct heard you {who}"}],
    })
    session.world.apply("CAA", "ctell~Other Line~Bob~hi")
    assert session.sent_lines == []                  # wrong channel
    session.world.apply("CAA", "ctell~Clan Sa~Friend~moo")
    assert session.sent_lines == ["ct heard you Friend"]


def test_round_event_rule():
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "round", "pace": "now",
        "actions": [{"type": "send", "text": "bash"}],
    })
    session.world.apply("FFF", "N~1~L~90")
    session.world.apply("FFF", "N~2~L~80")
    assert session.sent_lines == ["bash", "bash"]


def test_room_event_exposes_its_contents():
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "room", "pace": "now",
        "actions": [{"type": "log", "text": "here: {mobs}"}],
    })
    notes = []
    host.note = notes.append
    session.world.apply("DDD", "w~d~u")
    session.world.apply("HAA", "npc~Cur~a dog~kill #N")
    session.world.apply("FFF", "A~100")              # settles the room block
    assert notes == ["here: Cur"]


# --- state watches -----------------------------------------------------------

def test_watch_is_edge_triggered_across_a_real_combat_pattern():
    """3k.org sends two composites per round, so a level-triggered watch would
    fire twice per round the whole time you are hurt."""
    session, host, store = make()
    store.upsert({
        "kind": "watch", "watch_field": "hp_pct", "op": "lt", "value": "35",
        "pace": "now", "actions": [{"type": "send", "text": "flee"}],
    })
    session.world.apply("FFF", "B~100")
    session.world.apply("FFF", "A~90")
    assert session.sent_lines == []

    # the two-per-round pattern seen on the wire
    for hp in (30, 34, 28, 33, 20, 31):
        session.world.apply("FFF", f"A~{hp}")
    assert session.sent_lines == ["flee"], "edge-triggering failed"

    session.world.apply("FFF", "A~90")               # recovered
    session.world.apply("FFF", "A~10")               # crossed again
    assert session.sent_lines == ["flee", "flee"]


def test_watch_can_be_level_triggered_on_request():
    session, host, store = make()
    store.upsert({
        "kind": "watch", "watch_field": "hp_pct", "op": "lt", "value": "50",
        "edge": False, "pace": "now",
        "actions": [{"type": "send", "text": "ouch"}],
    })
    session.world.apply("FFF", "B~100")
    for hp in (40, 30, 20):
        session.world.apply("FFF", f"A~{hp}")
    assert session.sent_lines == ["ouch", "ouch", "ouch"]


def test_watch_validation():
    from mud.rules import Rule
    act = [{"type": "send", "text": "x"}]
    assert Rule(kind="watch", watch_field="nope", value="1",
                actions=act).validate().startswith("unknown field")
    assert Rule(kind="watch", watch_field="hp_pct", op="lt", value="abc",
                actions=act).validate().endswith("is not a number")
    assert Rule(kind="watch", watch_field="hp_pct", op="lt", value="35",
                actions=act).validate() is None


def test_disabling_an_event_rule_unsubscribes_it():
    session, host, store = make()
    rule, _ = store.upsert({
        "kind": "event", "event": "tell", "pace": "now",
        "actions": [{"type": "send", "text": "hi"}],
    })
    session.world.apply("BAB", "~A~x")
    assert session.sent_lines == ["hi"]

    store.upsert({**{k: getattr(rule, k) for k in ("id", "kind", "event",
                                                   "pace", "actions")},
                  "enabled": False})
    session.sent_lines.clear()
    session.world.apply("BAB", "~A~x")
    assert session.sent_lines == [], "handler survived being disabled"


# --- enemy: name and health, triggerable ------------------------------------

def test_enemy_event_fires_on_engage_and_disengage():
    session, host, store = make()
    notes = []
    host.note = notes.append
    store.upsert({
        "kind": "event", "event": "enemy",
        "actions": [{"type": "log", "text": "target: [{enemy}]"}],
    })
    session.world.apply("FFF", "K~Gabriel, archangel of Yesod {glowing}~L~100")
    session.world.apply("FFF", "K~")                 # combat ended
    assert notes == ["target: [Gabriel, archangel of Yesod {glowing}]",
                     "target: []"]


def test_round_rule_can_name_the_target_and_its_health():
    """The round event only carried {round}; the interesting part is who you
    are hitting and how hurt they are."""
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "round", "pace": "now",
        "actions": [{"type": "send", "text": "say {enemy} is at {enemy_pct}%"}],
    })
    session.world.apply("FFF", "K~a hulking orc~L~86~N~3")
    assert session.sent_lines == ["say a hulking orc is at 86%"]


def test_watch_on_enemy_health():
    session, host, store = make()
    store.upsert({
        "kind": "watch", "watch_field": "enemy_pct", "op": "lt", "value": "20",
        "pace": "now", "actions": [{"type": "send", "text": "kill {enemy}"}],
    })
    session.world.apply("FFF", "K~a goblin~L~90")
    assert session.sent_lines == []
    session.world.apply("FFF", "L~15")
    assert session.sent_lines == ["kill a goblin"]


def test_watch_on_enemy_name():
    session, host, store = make()
    store.upsert({
        "kind": "watch", "watch_field": "enemy", "op": "contains",
        "value": "archangel", "pace": "now",
        "actions": [{"type": "send", "text": "flee"}],
    })
    session.world.apply("FFF", "K~a goblin")
    assert session.sent_lines == []
    session.world.apply("FFF", "K~Gabriel, archangel of Yesod")
    assert session.sent_lines == ["flee"]


def test_a_name_cannot_be_compared_numerically():
    from mud.rules import Rule
    r = Rule(kind="watch", watch_field="enemy", op="lt", value="5",
             actions=[{"type": "send", "text": "x"}])
    assert "compare it with" in r.validate()


def test_context_is_available_to_any_rule():
    """A tell rule can report your health without any of it being scraped."""
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "tell", "pace": "now",
        "actions": [{"type": "send", "text": "tell {who} hp {hp_pct}% vs {enemy}"}],
    })
    session.world.apply("FFF", "B~100~A~40~K~a goblin")
    session.world.apply("BAB", "~Friend~you ok?")
    assert session.sent_lines == ["tell Friend hp 40.0% vs a goblin"]


def test_conditions_may_test_state_the_event_does_not_carry():
    """"on a round, only when the enemy is nearly dead" -- the round event
    carries only {round} of its own."""
    session, host, store = make()
    store.upsert({
        "kind": "event", "event": "round", "pace": "now",
        "conditions": [{"field": "enemy_pct", "op": "lt", "value": "20"}],
        "actions": [{"type": "send", "text": "kill {enemy}"}],
    })
    session.world.apply("FFF", "K~a goblin~L~90~N~1")
    assert session.sent_lines == []                  # still healthy
    session.world.apply("FFF", "L~12~N~2")
    assert session.sent_lines == ["kill a goblin"]


# --- timers -------------------------------------------------------------------


def timer_host(every=290.0, text="xp"):
    """A host with one timer rule and nothing else."""
    from mud.rules import Rule, RuleStore
    from mud.scripts import ScriptHost
    from mud.session import Session

    class Wire:
        def __init__(self):
            self.out = []

        def write(self, data):
            self.out.append(data)

    session = Session(sec_code=1)
    session._writer = Wire()
    host = ScriptHost(session, "/nonexistent")
    host.rules = RuleStore(host, "/nonexistent/rules.json")
    host.rules.rules = [Rule(kind="timer", name=text, every=every,
                             actions=[{"type": "send", "text": text}])]
    host.rules.register()
    return session, host


def beat(session):
    from mud import events
    session.bus.emit(events.TICK)


def test_a_timer_fires_when_it_comes_round():
    import time as _time
    session, host = timer_host()
    session.mip_seen = True
    beat(session)
    assert session._writer.out == [], "fired before it was due"
    host.rules._timers[0][1] = _time.monotonic() - 1
    beat(session)
    assert session._writer.out == [b"xp\r\n"]


def test_a_timer_does_not_fire_at_the_login_prompt():
    """The beat free-runs when there is no signal to lock onto, and that
    includes sitting at the login prompt -- where sending "xp" every 290
    seconds types it into the password box."""
    session, host = timer_host()
    for _ in range(20):
        beat(session)
    assert session._writer.out == []


def test_a_timer_waits_a_full_period_after_a_reload():
    """Due immediately would fire every timer at once on a reload, which for
    a reload you did not mean is a burst of commands you did not mean either."""
    import time as _time
    session, host = timer_host(every=290.0)
    due = host.rules._timers[0][1] - _time.monotonic()
    assert 289 < due <= 290


def test_a_timer_faster_than_the_beat_is_refused():
    """It is checked on the game's own two-second beat, so anything under one
    is a number the client cannot keep."""
    from mud.rules import Rule
    assert Rule(kind="timer", every=0.5,
                actions=[{"type": "send", "text": "x"}]).validate()
    assert Rule(kind="timer", every=290,
                actions=[{"type": "send", "text": "x"}]).validate() is None


def test_a_timer_renders_as_a_script():
    """The second door: click your way to something that works, then take the
    code and grow it."""
    from mud.rules import Rule
    code = Rule(kind="timer", name="xp", every=290,
                actions=[{"type": "send", "text": "xp"}]).as_python()
    assert "@every(290)" in code and 'send(f"xp")' in code
