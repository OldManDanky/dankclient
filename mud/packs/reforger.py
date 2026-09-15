"""Reforger: 3kdb's reforging shortcuts.

Written from 3kdb's modules/professions/reforger.tin.  The names are 3kdb's,
so somebody coming from it types what they always typed.
"""

#: Largest first: each reforge takes what it can and the next finishes off.
AMOUNTS = ("loads", "lots", "some", "little")


def to_defense(item, kind, where=""):
    for amount in AMOUNTS:
        send(f"reforge {item}{where} with {amount} from {kind} to defense")


def item_and_kind(m):
    """`ref shroud fire` -> ("shroud", "fire").  The type is always last."""
    item, _, kind = m["args"].rpartition(" ")
    return (item.strip(), kind) if item.strip() and kind else (None, None)


@alias("ref", mode="command")
def ref(m):
    item, kind = item_and_kind(m)
    if item is None:
        say("usage: ref <item> <type>, e.g. ref shroud fire")
        return
    to_defense(item, kind)


@alias("refg", mode="command")
def refg(m):
    item, kind = item_and_kind(m)
    if item is None:
        say("usage: refg <item> <type> -- for an item on the ground")
        return
    to_defense(item, kind, " on ground")


def knife():
    send("buy knife")
    send("reforge knife with little from edged to critical")
    send("dispose knife")


@alias("refk", mode="command")
def refk(_m):
    knife()


@alias("refs", mode="command")
def refs(_m):
    send("buy sword")
    send("reforge sword with little from edged to penetrate")
    send("dispose sword")


@alias("refk1", mode="command")
def refk1(_m):
    send("drop forge")
    send("unkeep knife")
    knife()
    send("get forge")
    send("keep forge")


@alias("refk2", mode="command")
def refk2(_m):
    send("remove shield")
    send("wear shield")
    send("drop forge")
    to_defense("shroud", "fire")
    send("get forge")
    send("keep forge")
