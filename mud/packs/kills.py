"""Kill stats: every kill, what it took and what it gave -- 3kdb's 3kReport.

Written from 3kdb's common/corpsetrig.tin, which notices a death, and
common/3kReport.tin, which tables them.  A kill is 3K's "Someone dealt the
killing blow to it." -- every kill in sixty captures has one.  3kdb also
wanted one of three death lines before it, and a creature that dies any
other way, a gun that does not gurgle in its own blood, was never counted.  3K's round counter and the clock say
how long it took; `xp` and `coins`, asked after each kill as 3kdb asks them,
say what it gave.  Their answers are kept off the screen when the pack asked,
never when you did.

`.kills` shows the last fifteen with totals and rates; `.kills 40`, `.kills
<mob>`, `.kills clear`, and `.kills ask off` to stop asking.  3kdb's
`3kReport` and `3kReport-clear` do the same.  The count and the xp an hour
sit in the Combat tracking panel, with the last kill.

Damage is 3K's own numbers, with its numbers setting on: "You hit Cur 1 time
for 9161 damage." dealt, "Cur hits you for 2537 damage!" taken -- raw, before
defenses, which is as far as damage can be followed from the text.  It is
counted from one kill to the next, so a fight with several creatures in it
is shared out kill by kill.

Left out: mob class, corpses used and guild GXP.  They need 3K's
eternal-only `cstats` or a guild line whose layout differs from guild to
guild.
"""

import time

from mud.triggers import Trigger

KILLING_BLOW = r"^(.+?) dealt the killing blow to (.+?)\.$"
#: 3K's numbers: what you dealt, and what was dealt you before defenses
HIT = r"^You hit .+ \d+ times? for ([\d,]+) damage\.$"
HURT = r"^.+ hits you for ([\d,]+) damage!$"
#: deaths that are not kills: a necromancer's undead and a mage's summons
NOT_KILLS = {"undead", "celestial lion", "undead wraith", "shadow panther",
             "something"}
SHOWN = 15
#: how long the answers to xp and coins are waited for, and kept hidden
ANSWER_WITHIN = 5.0
#: the answers hidden while the pack is the one asking
ANSWERS = (r"^You have [\d,]+ total xp\.$",
           r"^You need [\d,]+ experience to achieve your next level\.$",
           r"^You have [\d,]+ to spend\.$",
           r"^XP Gain for the last \d+ minutes: [\d,]+$",
           r"^At this rate you will level ",
           r"^You are carrying [\d,]+ coins in loose change\.$",
           r"^You have [\d,]+ coins in bags\.$",
           r"^You have [\d,]+ coins in the bank\.$")

kills = []
fight = {"base": 0, "last": 0, "began": None, "enemy": "", "dealt": 0, "taken": 0}
last = {"xp": None, "coins": None}
waiting = {"kill": None, "want": set(), "until": 0.0}


def number(text):
    return int(text.replace(",", ""))


def short(n):
    if n is None:
        return "-"
    # A high mortal's total xp runs to trillions.
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e4, "K")):
        if abs(n) >= size:
            size = 1e3 if unit == "K" else size
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + unit
    return f"{round(n):,}"


def asking():
    return keep.get("ask", True)


def hours(chosen):
    first, final = chosen[0], chosen[-1]
    began = first["at"] - (first["seconds"] or 0)
    return max(final["at"] - began, 60.0) / 3600


def xp_rate(chosen):
    gained = [k["xp"] for k in chosen if k["xp"] is not None]
    return sum(gained) / hours(chosen) if gained else None


def paint():
    # "kills: 0" from the start, so a loaded pack can be seen to be loaded.
    rate = xp_rate(kills) if kills else None
    lines = [f"kills: {len(kills)}" + (f"  {short(rate)} xp/hr" if rate else "")]
    if kills:
        k = kills[-1]
        said = [k["mob"][:24]]
        if k["rounds"]:
            said.append(f"{k['rounds']} rounds")
        if k.get("dealt"):
            said.append(f"{short(k['dealt'])} dealt")
        if k["xp"] is not None:
            said.append(f"{short(k['xp'])} xp")
        lines.append("last: " + "  ".join(said))
    status("\n".join(lines))


paint()


# --- asking 3K what a kill gave ----------------------------------------------------

def quiet(on):
    session.gags.remove_owner(owner)
    for pattern in ANSWERS if on else ():
        session.gags.add(Trigger(pattern, lambda _m=None: None, "regex", owner))


def ask(kill, want):
    waiting["kill"], waiting["want"] = kill, set(want)
    waiting["until"] = time.monotonic() + ANSWER_WITHIN
    quiet(True)
    for what in want:
        send(what)


def done():
    waiting["kill"], waiting["want"] = None, set()
    quiet(False)
    paint()


def answered(what):
    if what in waiting["want"]:
        waiting["want"].discard(what)
        if not waiting["want"]:
            done()


@every(1.0)
def expire():
    if waiting["want"] and time.monotonic() > waiting["until"]:
        done()


@trigger(r"^You have ([\d,]+) total xp\.$")
def total_xp(m):
    n, kill = number(m[1]), waiting["kill"]
    if (kill is not None and "xp" in waiting["want"] and kill["xp"] is None
            and last["xp"] is not None):
        # Less than before is xp spent, or a death: not this kill's to report.
        kill["xp"] = n - last["xp"] if n >= last["xp"] else None
    last["xp"] = n


@trigger(r"^At this rate you will level ")
def xp_answered(_m):
    answered("xp")


@trigger(r"^You are carrying ([\d,]+) coins in loose change\.$")
def coins(m):
    n, kill = number(m[1]), waiting["kill"]
    if (kill is not None and "coins" in waiting["want"] and kill["coins"] is None
            and last["coins"] is not None):
        kill["coins"] = n - last["coins"] if n >= last["coins"] else None
    last["coins"] = n


@trigger(r"^You have [\d,]+ coins in the bank\.$")
def coins_answered(_m):
    # The last of the three lines `coins` prints.
    answered("coins")


# --- a fight, and a kill -------------------------------------------------------------

@on("round")
def counting(n):
    if not n:
        # 3K can set the round to 0 before the death line arrives, so the end
        # of a fight is seen when the next one starts lower, not here.
        return
    if fight["began"] is None or n < fight["last"]:
        fight["base"], fight["began"] = n - 1, time.monotonic()
        if asking() and last["xp"] is None and not waiting["want"]:
            ask(None, ("xp", "coins"))          # where the first kill starts from
    fight["last"] = n
    if player.enemy:
        fight["enemy"] = player.enemy


@trigger(HIT)
def hit(m):
    fight["dealt"] += number(m[1])


@trigger(HURT)
def hurt(m):
    fight["taken"] += number(m[1])


@trigger(KILLING_BLOW)
def blow(m):
    killer, mob = m[1].strip(), m[2].strip()
    lower = mob.lower()
    if lower in NOT_KILLS or lower.endswith("jugger support mech"):
        return
    if fight["enemy"] and killer.lower() == fight["enemy"].lower():
        return                                   # the creature killed a summon
    now = time.monotonic()
    began = fight["began"]
    kill = {"mob": mob, "killer": killer,
            "rounds": max(fight["last"] - fight["base"], 1) if began else None,
            "seconds": round(now - began) if began else None,
            "dealt": fight["dealt"], "taken": fight["taken"],
            "xp": None, "coins": None, "at": time.time()}
    # The next creature in the same fight is counted from here.
    fight["base"], fight["began"] = fight["last"], now
    fight["dealt"] = fight["taken"] = 0
    kills.append(kill)
    paint()
    if asking():
        ask(kill, ("xp", "coins"))


# --- the report ----------------------------------------------------------------------

def seconds(s):
    if s is None:
        return "-"
    return f"{s}s" if s < 60 else f"{s // 60}m{s % 60:02d}s"


def report(arg):
    low = arg.strip().lower()
    if low == "clear":
        kills.clear()
        paint()
        say("kill stats cleared.")
        return
    if low in ("ask on", "ask off"):
        keep["ask"] = low == "ask on"
        keep.save()
        say("asking xp and coins after each kill." if keep["ask"]
            else "not asking xp or coins after kills; rounds and time still count.")
        return
    chosen, count = kills, SHOWN
    if low.isdigit():
        count = max(1, int(low))
    elif low:
        chosen = [k for k in kills if low in k["mob"].lower()]
    if not chosen:
        say("no kills yet." if not kills else f"no kills of {arg.strip()!r}.")
        return
    rows = [f"  {'Mob':<20} {'Killer':<12} {'Rnds':>4} {'Time':>6} {'Dealt':>7} "
            f"{'Taken':>7} {'XP':>7} {'Coins':>6}"]
    for k in chosen[-count:]:
        rows.append(f"  {k['mob'][:20]:<20} {k['killer'][:12]:<12} "
                    f"{k['rounds'] if k['rounds'] is not None else '-':>4} "
                    f"{seconds(k['seconds']):>6} {short(k.get('dealt') or None):>7} "
                    f"{short(k.get('taken') or None):>7} {short(k['xp']):>7} "
                    f"{short(k['coins']):>6}")
    n = len(chosen)
    rounds = [k["rounds"] for k in chosen if k["rounds"] is not None]
    times = [k["seconds"] for k in chosen if k["seconds"] is not None]
    xps = [k["xp"] for k in chosen if k["xp"] is not None]
    cash = [k["coins"] for k in chosen if k["coins"] is not None]
    shown = f" (the last {count})" if n > count else ""
    rows.append(f"  {n} kill{'s' if n != 1 else ''}{shown}"
                + (f"  |  {sum(rounds) / len(rounds):.1f} rounds" if rounds else "")
                + (f", {seconds(round(sum(times) / len(times)))} each" if times else ""))
    dealt = sum(k.get("dealt", 0) for k in chosen)
    taken = sum(k.get("taken", 0) for k in chosen)
    if dealt or taken:
        rows.append(f"  damage dealt {short(dealt)}, {short(dealt / n)} a kill"
                    + (f"  |  taken {short(taken)}, {short(taken / n)} a kill, "
                       "before defenses" if taken else ""))
    if xps:
        rows.append(f"  xp {short(sum(xps))}: {short(sum(xps) / len(xps))} a kill, "
                    f"{short(sum(xps) / hours(chosen))} an hour")
    if cash:
        rows.append(f"  coins {short(sum(cash))}: {short(sum(cash) / hours(chosen))} an hour")
    show(*rows)


@alias(".kills", mode="command")
def kills_command(m):
    report(m["args"])


@alias("3kReport", mode="command")
def three_k_report(m):
    report(m["args"])


@alias("3kReport-clear", mode="command")
def three_k_report_clear(_m):
    report("clear")
