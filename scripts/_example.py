"""Reference script -- NOT loaded.

Files whose names start with "_" are skipped, because this one logs every
tell, chat, room and combat round and that is a lot of noise to actually play
through.  Copy what you want into a file of your own, or rename this to
example.py to run it as-is.

Everything below is injected; no imports needed.  In the client, `/test <line>`
fires a text trigger without waiting for the MUD to say the thing, and
`/triggers` shows what is registered.
"""

# --- structured MIP events ---------------------------------------------------
# Tells, chat and room contents arrive as fields, so none of this is scraped.

@on("tell")
def announce_tell(t):
    if not t.from_me:
        log(f"tell from {t.who}: {t.message}")


@on("chat")
def announce_chat(c):
    log(f"[{c.channel}] {c.who}: {c.message}")


@on("room")
def describe_room(r):
    mobs = [o.name for o in r.mobs()]
    if mobs:
        log(f"{r.short or 'room'}: {', '.join(mobs)}")


# --- state watches -----------------------------------------------------------
# Edge-triggered: fires on the crossing, not on every update while below.

@when(lambda p: p.hp_pct is not None and p.hp_pct < 35)
def low_health():
    log(f"HP {player.hp_pct}% -- crossed 35%")


# --- the combat round counter (composite tag N) ------------------------------

@on("round")
def show_round(n):
    if n:
        log(f"round {n}: {player.enemy or '?'} at {player.enemy_pct}%")


# --- text triggers -----------------------------------------------------------
# The fallback for anything MIP does not carry.  Test with:
#   /test Grot has arrived
#   /test You feel a chill

@trigger(r"(?P<who>\w+) has arrived")
def arrival(m):
    log(f"arrival: {m['who']}")


@trigger("You feel a chill", mode="contains")
def chill(m):
    log("something is nearby")


@trigger("* tells you: *", mode="glob")
def any_tell(m):
    log("glob matched a tell line")


# --- aliases -----------------------------------------------------------------
# Expand what you type before it reaches the MUD.  Try:  k orc

@alias(r"^k (?P<target>.+)$")
def kill_alias(m):
    send(f"consider {m['target']}")
    send(f"kill {m['target']}")
