"""Trapper: traps and materials counted, and scrounging in your order.

Written from 3kdb's modules/professions/trapper.tin.  Looking in the rucksack
prints five lines; they are kept off the screen and drawn as one table, and
`.traps` draws it again.  The scrounge order is kept with the character,
where 3kdb forgot it at the end of a session.
"""

TRAPS = ("blind", "slow", "stun", "snare", "wound")
MATERIALS = ("metal", "wood", "hide")
WIDTH = 60

sack = {"traps": dict.fromkeys(TRAPS, 0), "stored": None, "room": None,
        "materials": dict.fromkeys(MATERIALS, 0), "items": None,
        "capacity": None, "charges": None}
trap = {"kind": "", "at": 0}
rounds = {"seen": 0, "last": 0}
scrounge = {"item": "", "next": 0}


def order():
    got = [m for m in keep.get("scrounge", []) if m in MATERIALS]
    return got + [m for m in MATERIALS if m not in got]


# --- what a fight does to a trap -----------------------------------------

@on("round")
def counting(n):
    if n and n != rounds["last"]:
        rounds["seen"] += 1
    rounds["last"] = n or 0


@trigger(r"^You reach into your rucksack, grab an? (\w+) trap, and launch it at ")
def launched(m):
    trap["kind"], trap["at"] = m[1].lower(), rounds["seen"]


@trigger(r"^TRAPPER: The (\w+) trap on ")
def ended(m):
    say(f"your {m[1].lower()} trap lasted {rounds['seen'] - trap['at']} rounds.")
    trap["kind"] = ""


# --- the rucksack ----------------------------------------------------------

gag(r"^You peer inside your rucksack to see what you have stored within\.$",
    mode="regex")
gag(r"^You have \d+/\d+ traps stored in your rucksack\.", mode="regex")
gag(r"^The traps stored are: .*\.$", mode="regex")
gag(r"Wood :\s*\d+\s+Metal :\s*\d+\s+Hide :\s*\d+ \(\d+/\d+ items\)",
    mode="regex")
gag(r"^You can launch \d+ traps right now\.$", mode="regex")


@trigger(r"^You have (\d+)/(\d+) traps stored in your rucksack\.")
def stored(m):
    sack["stored"], sack["room"] = int(m[1]), int(m[2])


@trigger(r"^The traps stored are: (.*)\.$")
def listed(m):
    sack["traps"] = dict.fromkeys(TRAPS, 0)
    for word in m[1].replace(",", " ").split():
        if word in sack["traps"]:
            sack["traps"][word] += 1


@trigger(r"Wood :\s*(\d+)\s+Metal :\s*(\d+)\s+Hide :\s*(\d+) \((\d+)/(\d+) items\)")
def materials(m):
    sack["materials"] = {"wood": int(m[1]), "metal": int(m[2]), "hide": int(m[3])}
    sack["items"], sack["capacity"] = int(m[4]), int(m[5])


@trigger(r"^You can launch (\d+) traps right now\.$")
def charges(m):
    sack["charges"] = int(m[1])
    draw()


def draw():
    if sack["charges"] is None:
        say("nothing counted yet -- look in your rucksack first")
        return
    title = (f"{session.who_am_i.upper()}'S TRAPSACK" if session.who_am_i
             else "TRAPSACK")
    traps = "  ".join(f"{k}: {v}" for k, v in sack["traps"].items())
    stuff = "  ".join(f"{k}: {sack['materials'][k]}" for k in MATERIALS)
    rows = [f"Materials  {stuff}  ({sack['items']}/{sack['capacity']} items)",
            f"Traps  {traps}  ({sack['stored']}/{sack['room']})",
            f"You may launch {sack['charges']} traps."]
    # As wide as the longest row, so a full rucksack never breaks the box.
    inner = max(WIDTH, *(len(r) + 2 for r in rows), len(title) + 2)
    rule = "+" + "-" * inner + "+"
    show(rule, f"|{title:^{inner}}|", rule,
         *(f"| {r:<{inner - 2}} |" for r in rows), rule)


@alias(".traps", mode="command")
def traps(_m):
    draw()


# --- scrounging --------------------------------------------------------------

def try_next():
    materials_ = order()
    if scrounge["next"] >= len(materials_):
        say(f"nothing to scrounge from {scrounge['item']}")
        scrounge["item"] = ""
        return
    send(f"scrounge {materials_[scrounge['next']]} from {scrounge['item']}")
    scrounge["next"] += 1


@alias(".scrounge", mode="command")
def scrounge_(m):
    if not m["args"]:
        say("usage: .scrounge <item>")
        return
    scrounge["item"], scrounge["next"] = m["args"], 0
    try_next()


@trigger(r"^You cannot find any suitable .+ on ")
def not_on_it(_m):
    if scrounge["item"]:
        try_next()


@trigger(r"^You find a nice chunk of .+ on .+ for your .+\.$")
def found(_m):
    scrounge["item"] = ""


def show_order():
    say("scrounge order: " + ", ".join(f"{i}. {m}" for i, m in
                                       enumerate(order(), start=1))
        + "  (.scrounge+ / .scrounge- <material> to move one)")


@alias(".scrounge-pref", mode="command")
def scrounge_pref(_m):
    show_order()


def move(m, by):
    material, now = m.get(1, "").lower(), order()
    if material not in now:
        say(f"'{m.get(1, '')}' is not a material: {', '.join(MATERIALS)}")
        return
    at = now.index(material)
    to = at + by
    if not 0 <= to < len(now):
        say(f"{material} is already {'first' if by < 0 else 'last'}")
        return
    now[at], now[to] = now[to], now[at]
    keep["scrounge"] = now
    keep.save()
    show_order()


@alias(".scrounge+", mode="command")
def scrounge_up(m):
    move(m, -1)


@alias(".scrounge-", mode="command")
def scrounge_down(m):
    move(m, +1)
