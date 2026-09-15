"""Corpse counts: where your corpses are, as 3kdb's corpse manager kept them.

Written from 3kdb's modules/corpsemanager/corpsemanager.tin.  The counts move
with 3K's own lines -- a corpse into the coffin, out of the freezer, handed
over by a packmule -- and are set outright whenever an inventory, or a look
inside a container, shows them.  The total and what is where sit in the
Session panel.

`corpse_select` uses the next corpse in 3kdb's order: coffin, freezer,
cooler, golem or servant, inventory, and the smuggled ones only when there is
nothing else.

Left out: the morgue runs (dcoffin), cooler_rotate, the SOL crypt boxes and
the necromancer's absorb sums -- they walk, pause steppers or belong to one
guild -- and the corpses-used-per-fight record.
"""

import re
import time

PLACES = ("coffin", "freezer", "cooler", "golem", "servant", "inventory",
          "smuggle")
SHORT = {"coffin": "C", "freezer": "F", "cooler": "Clr", "golem": "Gol",
         "servant": "Srv", "inventory": "I", "smuggle": "S"}
#: the most a freezer or a cooler holds
MOST_HELD = 50
#: "You have no corpse" looks in the inventory, but not more often than this
ASK_EVERY = 5.0

count = dict.fromkeys(PLACES, 0)
#: a container being looked inside: which, and until when its lines count
inside = {"place": "", "until": 0.0}
asked = {"at": 0.0}


def paint():
    total = sum(count.values())
    where = "  ".join(f"{SHORT[p]} {count[p]}" for p in PLACES if count[p])
    status(f"corpses: {total}" + (f"  ({where})" if where else ""))


def put(place, n):
    if place in ("freezer", "cooler"):
        n = min(n, MOST_HELD)
    count[place] = max(0, n)
    paint()


def add(place, by=1):
    put(place, count[place] + by)


def look_inside(place, seconds):
    inside["place"], inside["until"] = place, time.monotonic() + seconds
    put(place, 0)


def looking(place):
    return inside["place"] == place and time.monotonic() < inside["until"]


paint()


# --- the coffin ----------------------------------------------------------------

@trigger(r"the coffin's protective hold!$")
def into_coffin(_m):
    add("coffin")


@trigger(r"The coffin expels a corpse!")
def out_of_coffin(_m):
    add("coffin", -1)


@trigger(r"The coffin expels all its corpses!|There are no corpses in the coffin!")
def coffin_empty(_m):
    put("coffin", 0)


@trigger(r"You picked up (\d+) corpses? into the coffin\.")
def picked_up(m):
    add("coffin", int(m[1]))


@trigger(r"An enchanted coffin \((\d+)")
def coffin_seen(m):
    put("coffin", int(m[1]))


@trigger(r"Coffin\s*\[\s*\d+/\s*\d+\|.*\|\s*(\d+)c\]")
def coffin_bar(m):
    put("coffin", int(m[1]))


# --- Death's freezer -----------------------------------------------------------

@trigger(r"Death's Freezer.*\((\d+) corpses\)")
def freezer_seen(m):
    put("freezer", int(m[1]))


@trigger(r"frame causing it to get sucked in!$")
def into_freezer(_m):
    add("freezer")


@trigger(r"^You shake the frame and out drops")
def out_of_freezer(_m):
    add("freezer", -1)


@trigger(r"^There are no corpses in the freezer!$|"
         r"^There is no reason to '(?:de)?slab' here\.$")
def freezer_empty(_m):
    put("freezer", 0)


# --- the tech ultra-cooler -----------------------------------------------------

@trigger(r"^You activate the Ultra-Cooler to retrieve")
def out_of_cooler(_m):
    add("cooler", -1)


@trigger(r"^You place the .* into the Ultra-Cooler")
def into_cooler(_m):
    add("cooler")
    add("inventory", -1)


@trigger(r"^There is no more room in the Ultra-Cooler")
def cooler_full(_m):
    put("cooler", MOST_HELD)


@trigger(r"^The cooler does not contain a corpse\.$")
def cooler_empty(_m):
    put("cooler", 0)


@trigger(r"^The Tech Ultra-Cooler\. It is large and oblong\.")
def cooler_looked_at(_m):
    look_inside("cooler", 2.0)


@trigger(r" a preserved, .* of ")
def preserved(_m):
    if looking("cooler"):
        add("cooler")


# --- a golem or packmule -------------------------------------------------------

@trigger(r"The command is: inventory")
def golem_inventory(_m):
    look_inside("golem", 5.0)


@trigger(r"Estimated Capacity: ")
def golem_done(_m):
    inside["until"] = 0.0


@trigger(r"Your packmule gives you .*(?:corpse|remains)")
def from_packmule(_m):
    add("golem", -1)
    add("inventory")


# --- the priest's aerial servant -----------------------------------------------

@trigger(r"swirls slowly and reveals that it is carrying:$")
def servant_looked_at(_m):
    look_inside("servant", 4.0)


@trigger(r"^Aerial servant takes: .* corpse\.$")
def servant_takes(_m):
    add("servant")


@trigger(r"^The aerial servant drops an? .* corpse\.$|^You take .* corpse .* from ")
def servant_gives(_m):
    add("servant", -1)


@trigger(r"^Your aerial servant has no 'corpse' to drop\.$|"
         r"^The aerial servant drops everything\.$")
def servant_empty(_m):
    put("servant", 0)


# --- smuggled --------------------------------------------------------------------

@trigger(r"^Items you are currently smuggling \(.*\):")
def smuggle_looked_at(_m):
    look_inside("smuggle", 2.0)


@trigger(r"Smuggling\s*\[\s*\d+/\s*\d+\|.*\|\s*(\d+)c\]")
def smuggle_bar(m):
    put("smuggle", int(m[1]))


@trigger(r"^You smuggle away: .*corpse")
def smuggled(_m):
    add("smuggle")
    add("inventory", -1)


@trigger(r"^You unsmuggle: .*corpse")
def unsmuggled(_m):
    add("smuggle", -1)
    add("inventory")


# --- carried ---------------------------------------------------------------------

@trigger(r"^You drop .*(?:corpse|remains).*\.$")
def dropped(_m):
    add("inventory", -1)


@trigger(r"(?:corpse|remains).*: (?:Taken|Ok)\.$")
def taken(_m):
    add("inventory")


@trigger(r"Encumberance\s*\[\s*\d+/\s*\d+\|.*\|\s*(\d+)c\]")
def carried_bar(m):
    put("inventory", int(m[1]))


@trigger(r"^(.*\b(?:corpse|remains)\b.*)$")
def listed(m):
    """A line naming a corpse, while a container's contents are being shown."""
    text = m[1]
    if looking("golem"):
        many = re.search(r"\{(\d+)\}", text)
        add("golem", int(many.group(1)) if many else 1)
    elif looking("cooler") and re.match(r"The .*(?:corpse|remains) of ", text):
        add("cooler")
    elif looking("smuggle") and text.startswith(">"):
        add("smuggle")
    elif looking("servant") and re.match(r"\s*\d+\).* corpse", text):
        add("servant")


@trigger(r"^You have no (?:corpse|remains)\.")
def none_left(_m):
    if time.monotonic() - asked["at"] >= ASK_EVERY:
        asked["at"] = time.monotonic()
        send("i")


# --- commands --------------------------------------------------------------------

@alias(".corpses", mode="command")
def corpses(m):
    what = m["args"].lower()
    if what == "check":
        send("i")
        return
    if what == "reset":
        for place in PLACES:
            count[place] = 0
        paint()
        say("every count is back to 0.")
        return
    total = sum(count.values())
    show(f"  {total} corpses",
         *(f"    {place:<10} {count[place]}" for place in PLACES if count[place]),
         "  .corpses check looks in your inventory; .corpses reset starts again.")


@alias("corpse_select", mode="command")
def corpse_select(_m):
    if count["coffin"]:
        send("unwrap")
    elif count["freezer"]:
        send("deslab")
    elif count["cooler"]:
        send("uncooler corpse")
    elif count["golem"]:
        send("golem drop corpse")
    elif count["servant"]:
        send("=drop corpse")
    elif count["inventory"]:
        send("unkeep corpse")
        send("drop corpse")
    elif count["smuggle"]:
        send("smuggle remove corpse")
        send("drop corpse")
    else:
        say("no corpses counted -- .corpses check to look")
