"""Transmuter: the satchel burned and upgraded, and the colour resets counted.

Written from 3kdb's modules/professions/transmuter.tin, with the satchel
reader and component table from its helpers.  3kdb read the satchel and then
waited a fixed four seconds; here the burn starts when `stashlist` has
finished answering.

3kdb's commands disagreed about how many items make the next quality.  This
follows transmute_ug, its newest: two poor make an average at any level;
above that it takes three, four and five below level 100, and two, three and
four at 100.
"""

NEXT = {"poor": "average", "average": "good", "good": "superior",
        "superior": "legendary"}


def needed(quality, lvl):
    if quality == "poor":
        return 2
    step = {"average": 3, "good": 4, "superior": 5}[quality]
    return step - 1 if lvl == 100 else step


#: (component, the level it can first be worked, the level it stops giving
#: profession experience) -- 3kdb's helpers/data_crafting.tin.
COMPONENTS = (
    ('aquamarine', 1, 10),
    ('aquamarine dust', 1, 10),
    ('copper shards', 1, 10),
    ('morganite', 1, 10),
    ('morganite dust', 1, 10),
    ("tiger's eye", 1, 10),
    ("tiger's eye dust", 1, 10),
    ('fragment of light', 2, 12),
    ('fragment of water', 5, 15),
    ('fragment of shadow', 6, 16),
    ('bronze shards', 7, 15),
    ("cat's eye", 7, 15),
    ("cat's eye dust", 7, 15),
    ('eye of flame', 7, 15),
    ('garnet', 7, 15),
    ('garnet dust', 7, 15),
    ('fragment of might', 9, 19),
    ('alexandrite', 10, 20),
    ('alexandrite dust', 10, 20),
    ('eye of frost', 10, 20),
    ('iron shards', 10, 20),
    ('fragment of rejuvenation', 12, 22),
    ('fragment of rage', 13, 23),
    ('fragment of soul', 15, 25),
    ('steel shards', 15, 25),
    ('fragment of the unseen', 18, 28),
    ('beryl', 20, 30),
    ('beryl dust', 20, 30),
    ('eye of earth', 20, 30),
    ('pyrite', 20, 30),
    ('pyrite dust', 20, 30),
    ("roan's tears", 20, 30),
    ('silver shards', 20, 30),
    ('tourmaline', 20, 30),
    ('tourmaline dust', 20, 30),
    ('fragment of ascension', 21, 31),
    ('fragment of blasting', 23, 33),
    ('fragment of damnation', 24, 34),
    ('amethyst', 25, 35),
    ('amethyst dust', 25, 35),
    ('eye of air', 25, 35),
    ('gold shards', 25, 35),
    ("happy ed's tears", 25, 35),
    ('topaz', 25, 35),
    ('topaz dust', 25, 35),
    ('fragment of willy', 27, 37),
    ('fragment of destruction', 28, 38),
    ('fragment of compassion', 30, 40),
    ('fragment of knowledge', 32, 42),
    ('core of flame', 33, 43),
    ('essence of light', 33, 43),
    ('heliodor', 33, 43),
    ('heliodor dust', 33, 43),
    ('hematite', 33, 43),
    ('hematite dust', 33, 43),
    ('mithril shards', 33, 43),
    ('essence of water', 36, 46),
    ('essence of shadow', 37, 47),
    ('essence of might', 40, 50),
    ('core of frost', 42, 52),
    ('peridot', 42, 52),
    ('peridot dust', 42, 52),
    ('titanium shards', 42, 52),
    ('essence of rejuvenation', 43, 53),
    ('essence of rage', 44, 54),
    ('essence of soul', 46, 56),
    ('essence of the unseen', 49, 59),
    ('core of earth', 50, 60),
    ('ebon shards', 50, 60),
    ('essence of ascension', 52, 62),
    ('essence of blasting', 54, 64),
    ('adamantim shards', 55, 65),
    ('core of air', 55, 65),
    ('essence of damnation', 55, 65),
    ('pearl', 55, 65),
    ('pearl dust', 55, 65),
    ('essence of willy', 58, 68),
    ('essence of destruction', 59, 69),
    ("ghoti's tears", 60, 70),
    ('obsidian shards', 60, 70),
    ('opal', 60, 70),
    ('opal dust', 60, 70),
    ('essence of compassion', 61, 71),
    ('essence of knowledge', 63, 73),
    ('star of flame', 65, 75),
    ('nethernium shards', 65, 75),
    ('heart of light', 66, 76),
    ('heart of water', 69, 79),
    ('heart of shadow', 70, 80),
    ('heart of might', 73, 83),
    ('diamond', 73, 83),
    ('diamond dust', 73, 83),
    ('star of frost', 73, 83),
    ('shansabyks tears', 73, 83),
    ('voidstone shards', 73, 83),
    ('heart of rejuvenation', 76, 86),
    ('heart of rage', 77, 87),
    ('heart of soul', 79, 89),
    ('emerald', 80, 90),
    ('emerald dust', 80, 90),
    ('star of air', 80, 90),
    ('star of earth', 80, 90),
    ('sapphire dust', 80, 90),
    ('sapphire', 80, 90),
    ('phasemetal shards', 80, 90),
    ('heart of the unseen', 82, 92),
    ('heart of ascension', 85, 95),
    ('heart of blasting', 87, 97),
    ('heart of damnation', 88, 98),
    ('chaostone shards', 90, 100),
    ('ruby', 90, 100),
    ('heart of willy', 91, 101),
    ('heart of destruction', 92, 102),
    ('heart of compassion', 94, 104),
    ('heart of knowledge', 96, 106),
    ('mithril ore', 33, 43),
    ('titanium ore', 42, 52),
    ('ebon ore', 50, 60),
    ('obsidian ore', 60, 70),
    ('nethernium ore', 65, 75),
    ('voidstone ore', 73, 83),
    ('phasemetal ore', 80, 90),
    ('chaostone ore', 90, 100),
)

#: mode -> (what it does, which qualities it lifts)
MODES = {
    "consolidate": ("up to superior, everything your level can work",
                    ("poor", "average", "good")),
    "consolidate-leg": ("up to legendary, everything your level can work",
                        ("poor", "average", "good", "superior")),
    "train": ("up to superior, only what still gives profession experience",
              ("poor", "average", "good")),
    "train-leg": ("up to legendary, only what still gives profession "
                  "experience", ("poor", "average", "good", "superior")),
}


def workable(mode, lvl, lo, hi):
    if mode == "train":
        return lo <= lvl < hi
    if mode == "train-leg":
        return lo <= lvl <= hi
    return lvl >= lo


# --- reading the satchel -----------------------------------------------------

satchel = {"rows": None, "got": None}
COLUMNS = ("total", "legendary", "superior", "good", "average", "poor")


@trigger(r"^(.+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
         r"\s*(\d+)\s*\|\s*(\d+)\s*\|")
def satchel_row(m):
    if satchel["rows"] is not None:
        name = " ".join(m[1].lower().split())
        satchel["rows"][name] = dict(zip(COLUMNS, (int(m[i]) for i in range(2, 8))))


@trigger(r"^You have \d+/\d+ items in your satchel\.")
def satchel_end(_m):
    if satchel["rows"] is not None:
        satchel["got"], satchel["rows"] = satchel["rows"], None


async def read_satchel(timeout=8.0):
    satchel["rows"], satchel["got"] = {}, None
    send("stashlist", HIGH, NOW)
    waited = 0.0
    while satchel["got"] is None and waited < timeout:
        await wait(0.1)
        waited += 0.1
    if satchel["got"] is None:
        satchel["rows"] = None
        say("stashlist did not answer, so nothing was transmuted.")
    return satchel["got"]


# --- burning -----------------------------------------------------------------

burn = {"count": None}
#: How long the last transmutes of a burn get to answer before it is counted.
SETTLE = 4.0


@trigger(r"Pfffzzzt!\s+You transmute:")
def zapped(_m):
    if burn["count"] is not None:
        burn["count"] += 1


def upgrade(name, quality, available, lvl):
    n = needed(quality, lvl)
    for _ in range(available // n):
        for _ in range(n):
            send(f"unstash {quality} {name}")
        send(f"transmute {n} {name} quality to {NEXT[quality]}")


def burn_help():
    show("  transmute_burn <mode> transmutes what is in your satchel:",
         *(f"    {mode:<16} {what}" for mode, (what, _q) in MODES.items()))


@alias("transmute_burn", mode="command")
async def transmute_burn(m):
    mode = m["args"].lower()
    if mode not in MODES:
        burn_help()
        return
    if burn["count"] is not None:
        say("a burn is already running.")
        return
    lvl = await fresh_level()
    if lvl is None:
        say("profs did not say a Transmuter level, so nothing was transmuted.")
        return
    say(f"transmuting materials: {mode}, level {lvl}")
    have = await read_satchel()
    if have is None:
        return
    burn["count"] = 0
    try:
        for name, lo, hi in COMPONENTS:
            counts = have.get(name)
            if not counts or not counts["total"] or not workable(mode, lvl, lo, hi):
                continue
            for quality in MODES[mode][1]:
                upgrade(name, quality, counts[quality], lvl)
        await wait(SETTLE)
        say(f"you transmuted {burn['count']} materials.")
        send("stash all")
    finally:
        burn["count"] = None


@alias("transmute_burn2", mode="command")
async def transmute_burn2(m):
    quality = m["args"].lower()
    if quality not in ("superior", "legendary"):
        show("  transmute_burn2 superior|legendary transmutes everything in "
             "your satchel except ore, all at once per item.")
        return
    have = await read_satchel()
    if have is None:
        return
    for name, counts in have.items():
        if name.endswith(" ore") or not counts["total"]:
            continue
        send(f"unstash all {name}")
        send(f"transmute all {name} quality to {quality}")
        send("stash all")


@alias("transmute_ug", mode="command")
async def transmute_ug(m):
    item, _, quality = m["args"].lower().rpartition(" ")
    if not item.strip() or quality not in NEXT:
        show("  transmute_ug <item> <quality> lifts one lot to the next quality,",
             "  e.g. transmute_ug heart of soul average  (makes a good one).",
             "  Qualities: poor, average, good, superior.")
        return
    lvl = level()
    if lvl is None:
        lvl = await fresh_level()
    n = needed(quality, lvl or 0)
    for _ in range(n):
        send(f"unstash {quality} {item.strip()}")
    send(f"transmute {n} {item.strip()} quality to {NEXT[quality]}")
    send("stash all")


@alias("transmute_ratios", mode="command")
def transmute_ratios(_m):
    show("  Transmuting ratios, level 100      Levels 0-99",
         "  4 crude    = 3 poor                4 crude    = 3 poor",
         "  3 poor     = 2 average             3 poor     = 2 average",
         "  2 average  = 1 good                3 average  = 1 good",
         "  3 good     = 1 superior            4 good     = 1 superior",
         "  4 superior = 1 legendary           5 superior = 1 legendary")


# --- colour resets -----------------------------------------------------------

resets = []


@trigger(r"^Your transmuter's stone bursts with (\d+) new colours!$")
def burst(m):
    resets.append(int(m[1]))


@trigger(r"Transmuters can convert crafting components from one item to "
         r"another, usually at a cost\.")
def hint(_m):
    say("transmuter-stats shows this login's colour resets.")


@alias("transmuter-stats", mode="command")
def transmuter_stats(_m):
    at = f", level {level()}" if level() else ""
    lines = [f"  Transmuter{at}"]
    if not resets:
        lines.append("  Your colours have not reset this login.")
    else:
        lines.append(f"  {len(resets)} resets, {sum(resets) / len(resets):.2f} "
                     "stones each on average")
        for stones in range(1, max(6, max(resets)) + 1):
            times = resets.count(stones)
            lines.append(f"    {stones} stones: {times} times "
                         f"({100 * times / len(resets):.0f}%)")
    show(*lines)
