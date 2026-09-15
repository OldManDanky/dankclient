"""Herbologist: what each herb does, and how long it lasted.

Written from 3kdb's modules/professions/herbologist.tin.  3kdb wrote each
herb's effect into 3K's text wherever the herb was named; the client does not
rewrite 3K's lines, so `.herbs` lists them instead, and the effect is in the
line that says how long a herb lasted.
"""

import time

EFFECTS = {
    "pinnacle nettle": "+dodge",
    "ginkgo biloba": "+free cast",
    "yellow pom weed": "+50hp",
    "lightning wort": "+attack speed",
    "blood's eye": "+critical hit",
    "meadowsweet": "sp/hp regen",
}

eaten = {}      # herb -> when it was eaten
lasted = {}     # herb -> seconds, each time


@trigger(r"^You eat the (.+?)\.")
def ate(m):
    herb = m[1].lower()
    if herb in EFFECTS:
        eaten[herb] = time.monotonic()


@trigger(r"^The effects of the (.+?) wear off\.")
def wore_off(m):
    herb = m[1].lower()
    start = eaten.pop(herb, None)
    if start is None:
        return
    seconds = round(time.monotonic() - start)
    lasted.setdefault(herb, []).append(seconds)
    at = f" at level {level()}" if level() else ""
    say(f"{herb} ({EFFECTS[herb]}) lasted {seconds} seconds{at}.")


@alias(".herbs", mode="command")
def herbs(_m):
    rows = []
    for herb, effect in EFFECTS.items():
        times = lasted.get(herb)
        seen = (f"lasted {times[-1]}s last time, "
                f"{round(sum(times) / len(times))}s on average") if times else ""
        rows.append(f"  {herb:<17} {effect:<15} {seen}".rstrip())
    show(*rows)
