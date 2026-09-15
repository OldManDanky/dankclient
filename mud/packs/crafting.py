"""Crafting helpers: 3kdb's crafting shortcuts, for any character.

Written from 3kdb's modules/crafting -- assemble.tin, smelter.tin,
blacksmith_forge.tin, enchanter.tin and crafting.tin -- with its gem recipes
and jewel table.  3kdb loads these whatever the profession, so here they are
ticked per character beside it.

Left out: the miner and farmer steppers and the wrangler's gem estimate,
which are large and need what the client does not keep; and 3kdb's `ln` and
the forge's `out`, short words a player may already use.
"""

import asyncio
import time

from mud.packs._craft_data import GEMS, JEWELS

#: the order the satchel's columns come in, after the total
QUALITIES = ("legendary", "superior", "good", "average", "poor")
TOMES = ("chef", "miner", "enchanter", "wrangler", "farmer", "blacksmith")
VOLUMES = {"i", "ii", "iii", "1", "2", "3", "one", "two", "three"}
#: an autosmelt that never hears "No objects found." still stops
MOST_SMELTS = 200
#: how long a moulding's ingredient list is listened for after examining it
FILL_WINDOW = 2.0
#: how long the kiln gets to say it made the gem
KILN_WAIT = 30.0


# --- assembling ------------------------------------------------------------------

satchel = {"rows": None, "done": False}


@trigger(r"^(Essence|Fragment) Of (.+?)\s*\|\s*\d+\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
         r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|")
def assembly_row(m):
    if satchel["rows"] is not None:
        satchel["rows"].append((m[1].lower(), m[2].strip().lower(),
                                [int(m[i]) for i in range(3, 8)]))


@trigger(r"^You have \d+/\d+ items in your satchel\.")
def satchel_end(_m):
    if satchel["rows"] is not None:
        satchel["done"] = True


@alias("assembler", mode="command")
async def assembler(_m):
    satchel["rows"], satchel["done"] = [], False
    send("stashlist", HIGH, NOW)
    for _ in range(80):
        if satchel["done"]:
            break
        await wait(0.1)
    rows, satchel["rows"] = satchel["rows"], None
    made = 0
    for shape, kind, counts in rows:
        for quality, have in zip(QUALITIES, counts):
            while have >= 5:
                send(f"unstash 5 {quality} {shape} of {kind}")
                send(f"assemble {shape} of {kind}")
                send("stash all")
                have -= 5
                made += 1
    say(f"assembling {made}." if made
        else "nothing in the satchel has five of a kind to assemble.")


# --- smelting ----------------------------------------------------------------------

smelt = {"ore": "", "rounds": 0}


def next_smelt():
    if smelt["rounds"] >= MOST_SMELTS:
        say(f"stopped after {MOST_SMELTS} rounds of smelting.")
        smelt["ore"] = ""
        return
    smelt["rounds"] += 1
    send(f"unstash2 all worst {smelt['ore']} ore")


@alias("autosmelt", mode="command")
def autosmelt(m):
    ore = m["args"].lower().strip()
    if ore.endswith(" ore"):
        ore = ore[:-4].strip()
    if not ore or ore == "off":
        say(f"stopped smelting {smelt['ore']} ore." if smelt["ore"] else
            "usage: autosmelt <ore>, e.g. autosmelt iron -- autosmelt off stops")
        smelt["ore"] = ""
        return
    smelt["ore"], smelt["rounds"] = ore, 0
    next_smelt()


@trigger(r"^You found: \[(\d+)\] \[(\w+)\] <[A-Za-z ]+ ore>")
def found_ore(m):
    if not smelt["ore"]:
        return
    n, quality = int(m[1]), m[2].lower()
    if n > 10:
        send(f"{n} insert {quality} {smelt['ore']} ore")
        send("smelt")
        send("get all")
        send("stash all")
    else:
        ore, smelt["ore"] = smelt["ore"], ""
        send("stash all")
        say(f"{n} {quality} {ore} ore is too little to smelt; stopped.")


@trigger(r"^You stuff .+ components into your crafting satchel\.")
def stuffed(_m):
    if smelt["ore"]:
        next_smelt()


@trigger(r"^No objects found\.")
def none_found(_m):
    if smelt["ore"]:
        say(f"no more {smelt['ore']} ore; done.")
        smelt["ore"] = ""
    if gem["checking"]:
        gem["missing"] = True


# --- the forge and mouldings -------------------------------------------------------

forge = {"on": False, "filling_until": 0.0, "filled": False}


@alias("forge-on", mode="command")
def forge_on(_m):
    forge["on"] = True
    say("forge on: examine a moulding and it is filled and fired, "
        "again and again.  forge-off stops.")


@alias("forge-off", mode="command")
def forge_off(_m):
    forge["on"] = False
    say("forge off.")


async def fire_soon():
    await wait(2)
    send("fire")


@trigger(r"-INGREDIENTS-")
def ingredients(_m):
    # The moulding goes in now, before the ingredients listed under this
    # line, as 3kdb does; only the firing waits.
    if forge["on"]:
        send("insert moulding")
        asyncio.get_running_loop().create_task(fire_soon())


@trigger(r"^(\d+) ([A-Za-z' ]+?)\s*$")
def ingredient(m):
    if forge["on"]:
        quality = "worst"
    elif time.monotonic() < forge["filling_until"]:
        quality = "best"
    else:
        return
    n, name = int(m[1]), m[2].strip()
    for _ in range(n):
        send(f"unstash2 {quality} {name}")
    for _ in range(n):
        send(f"insert {name}")


@alias("fill-moulding", mode="command")
def fill_moulding(_m):
    forge["filling_until"], forge["filled"] = time.monotonic() + FILL_WINDOW, True
    send("examine moulding")
    send("insert moulding")


@trigger(r"You have created something new!")
def created(_m):
    if gem["making"]:
        send("retrieve gem")
        send("keep gem")
        say(f"made the gem of {gem['making']}.")
        gem["making"] = ""
    elif forge["on"]:
        send("retrieve all")
        send("exa moulding")
    elif forge["filled"]:
        forge["filled"] = False
        send("retrieve all")


# --- gems ----------------------------------------------------------------------------

gem = {"making": "", "checking": False, "missing": False}


def gem_named(text):
    key = " ".join(text.lower().split())
    return next((g for g in GEMS if g[0].lower() == key), None)


@alias("make-gem", mode="command")
async def make_gem(m):
    wanted = m["args"].strip()
    found = gem_named(wanted) if wanted else None
    if found is None:
        near = [g[0] for g in GEMS if wanted and wanted.lower() in g[0].lower()]
        if not wanted:
            say("usage: make-gem <gem>, e.g. make-gem minor might -- the "
                "legendary materials must be in your satchel")
        else:
            say(f"no gem called {wanted!r}"
                + (f"; perhaps {', '.join(near[:8])}" if near else "")
                + ".  gem-lookup <word> finds one.")
        return
    if gem["making"]:
        say(f"already making the gem of {gem['making']}.")
        return
    name, _lo, _hi, jewels, fragment, _effect = found
    parts = [j.lower() for j in jewels] + ([fragment.lower()] if fragment else [])
    gem["making"] = name
    try:
        say(f"making the gem of {name} from {', '.join(parts)}.")
        for part in parts:
            gem["checking"], gem["missing"] = True, False
            send(f"unstash2 legendary {part}")
            await wait(1.0)
            gem["checking"] = False
            if gem["missing"]:
                say(f"no legendary {part} in your satchel, so no gem.  "
                    "Anything already taken out is in your inventory.")
                return
        if not await go_to("enchanter_shop"):
            return
        send(f"buy gem of {name.lower()}")
        await wait(1.0)
        if not await go_to("enchanter_kiln"):
            return
        for part in parts:
            send(f"insert {part}")
        send("insert moulding")
        send("fire")
        began = time.monotonic()
        while gem["making"] and time.monotonic() - began < KILN_WAIT:
            await wait(0.1)
        if gem["making"]:
            say("the kiln has not said it made anything.")
    finally:
        gem["checking"], gem["making"] = False, ""


@alias("gem-lookup", mode="command")
def gem_lookup(m):
    word = m["args"].strip().lower()
    if not word:
        say("usage: gem-lookup <word or level>, e.g. gem-lookup wis, "
            "gem-lookup fire, gem-lookup 48")
        return
    hits = [g for g in GEMS if word in g[0].lower() or word in g[5].lower()
            or (word.isdigit() and int(word) in (g[1], g[2]))]
    if not hits:
        say(f"no gem or effect matching {word!r}.")
        return
    rows = []
    for name, lo, hi, jewels, fragment, effect in hits:
        rows.append(f"  {name}  levels {lo}-{hi}" + (f", {effect}" if effect else ""))
        rows.append(f"      {', '.join(jewels)}" + (f" + {fragment}" if fragment else ""))
    show(*rows)


@alias("jewel-lookup", mode="command")
def jewel_lookup(m):
    word = m["args"].strip().lower()
    if not word:
        say("usage: jewel-lookup <word or level>, e.g. jewel-lookup heart, "
            "jewel-lookup 48")
        return
    hits = [j for j in JEWELS if word in j[0] or any(word in t for t in j[3])
            or (word.isdigit() and int(word) in (j[1], j[2]))]
    if not hits:
        say(f"no jewel matching {word!r}.")
        return
    rows = []
    for name, lo, trivial, into in hits:
        rows.append(f"  {name}  levels {lo}-{trivial}")
        rows.append(f"      transmutes into {', '.join(into)}")
    show(*rows)


# --- tomes ---------------------------------------------------------------------------

def volume(m, verb):
    got = m["args"].strip().lower()
    if got not in VOLUMES:
        say(f"usage: {verb} <i|ii|iii> -- or 1, 2, 3, or one, two, three")
        return None
    return got


@alias("borrow-tomes", mode="command")
def borrow_tomes(m):
    v = volume(m, "borrow-tomes")
    for tome in TOMES if v else ():
        send(f"borrow {tome} volume {v}")


@alias("buy-tomes", mode="command")
def buy_tomes(m):
    v = volume(m, "buy-tomes")
    for tome in TOMES if v else ():
        send(f"buy {tome} volume {v}")


@alias("box-tomes", mode="command")
def box_tomes(m):
    v = volume(m, "box-tomes")
    for tome in TOMES if v else ():
        send(f"get {tome} volume {v} from box")
