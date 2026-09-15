"""Marshal: the standard's charges, and rallycry once a fight if asked.

Written from 3kdb's modules/professions/marshal.tin.  3kdb counted charges
and, every two seconds of a fight, used whichever rallycries the player had
switched on.  Two things are different here:

* each rallycry goes out once a fight, between rounds 7 and 15, rather than
  every two seconds for as long as those rounds last;
* 3kdb also waited for its damage tracker to say the fight was a long one.
  The client has no damage tracker, so the rounds alone decide.

All four start off, as in 3kdb: a rallycry is a choice, not a default.
"""

MOST = 12
KINDS = ("offensive", "defensive", "heal", "spirit")
FIRST_ROUND, LAST_ROUND = 7, 15

standard = {"charges": None}
used = set()                    # the rallycries this fight has had


@trigger(r"^A surge of leadership rushes through your veins,")
def surge(_m):
    have = standard["charges"] or 0
    standard["charges"] = MOST if have > MOST - 4 else have + 4


@trigger(r"A Marshal's Standard \((\d+) glowing of 12 total gems\)")
def counted(m):
    standard["charges"] = int(m[1])


@trigger(r"^You have already exhausted the magic of the marshal's standard!$")
def exhausted(_m):
    standard["charges"] = 0


def chosen():
    return [k for k in KINDS if keep.get(k)]


@alias(".standard", mode="command")
def show_standard(_m):
    have = standard["charges"]
    said = (f"{have} of {MOST} charges" if have is not None
            else "charges not seen yet -- look at the standard to count them")
    say(f"{said}; rallycry once a fight: {', '.join(chosen()) or 'none'}")


@alias(".rallycry", mode="command")
def rallycry(m):
    kind, switch = m.get(1, "").lower(), m.get(2, "").lower()
    if kind not in KINDS or switch not in ("on", "off"):
        say(f"usage: .rallycry <{'|'.join(KINDS)}> on|off -- "
            f"now: {', '.join(chosen()) or 'none'}")
        return
    keep[kind] = switch == "on"
    keep.save()
    say(f"rallycry {kind} {switch}")


@on("round")
def round_(n):
    if not n or not player.enemy:
        used.clear()
        return
    if not FIRST_ROUND <= n <= LAST_ROUND or not standard["charges"]:
        return
    for kind in chosen():
        if kind in used:
            continue
        used.add(kind)
        if kind == "offensive":
            # 3K takes the creature by the last word of its name.
            send(f"rallycry offensive {player.enemy.split()[-1].lower()}")
        else:
            send(f"rallycry {kind}")
