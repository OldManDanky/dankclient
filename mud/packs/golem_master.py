"""Golem Master: a golem built a part per corpse, and filled.

Written from 3kdb's modules/professions/golem_master.tin.  3kdb leaned on a
`ktrig` alias -- "at the next killing blow, do this" -- that lives in one
player's own files rather than in 3kdb's common ones, so the pack does that
part itself.

3kdb rebuilt two golems it knew by name.  Golems are called whatever yours
are called, so here an expired golem is rebuilt as the kind last built.
"""

golem = {"kind": "", "next": [], "filling": False, "gives": 0}

#: A fill that never hears "can't carry" still stops.
MOST_GIVES = 60


def at_next_kill(*commands):
    golem["next"] = list(commands)


def build(kind):
    golem["kind"] = kind
    at_next_kill("golemize corpse head", "wrap", "get all")
    say(f"building a {kind} golem: the next corpse gives its head")


@alias("build_golem", mode="command")
def build_golem(m):
    if not m["args"]:
        doing = f" -- building a {golem['kind']} golem" if golem["next"] else ""
        say("usage: build_golem <kind>, e.g. build_golem companion" + doing)
        return
    build(m["args"])


@trigger(r"dealt the killing blow")
def killed(_m):
    commands, golem["next"] = golem["next"], []
    for command in commands:
        send(command)


@trigger(r"^You quickly set to work and deftly remove the (head|torso|limbs) "
         r"from corpse\.$")
def part(m):
    if m[1] == "head":
        at_next_kill("golemize corpse torso", "wrap", "get all")
    elif m[1] == "torso":
        at_next_kill("golemize corpse limbs", "wrap", "get all")
    elif golem["kind"]:
        send(f"golem build {golem['kind']}")
        at_next_kill("wrap all", "get all", "put all in disc")


@trigger(r"^Your golem .+ has expired\.$")
def expired(_m):
    if golem["kind"]:
        build(golem["kind"])


def give():
    golem["gives"] += 1
    send("unkeep preservation")
    send("give preservation to golem")


@alias("fill_golem", mode="command")
def fill_golem(_m):
    golem["filling"], golem["gives"] = True, 0
    give()


@trigger(r"^You unkeep ")
def unkept(_m):
    if not golem["filling"]:
        return
    if golem["gives"] >= MOST_GIVES:
        golem["filling"] = False
        say(f"stopped filling after {MOST_GIVES} preservations")
        return
    give()


@trigger(r"Golem can't carry that much more\.")
def full(_m):
    if golem["filling"]:
        golem["filling"] = False
        send("golem inventory")
        send("i")
