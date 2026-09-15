"""Packs: 3kdb's modules, written again as scripts a character loads.

Two kinds, both chosen on the character screen.  A character's *profession*:
3kdb's modules/professions, one per character, which 3kdb picks by what
`profs` names first.  And any *extras* -- the corpse counts and the crafting
helpers -- which 3kdb loads whatever the profession.

3kdb's modules are TinTin++ programs -- variables, #if, #math, lists, tables
drawn to a fixed width -- and the TinTin++ importer brings about a fifth of
the professions across.  So each is written again here as a script, run by the
same ScriptHost as a player's own files.

A pack is a script like any other, with a few more names in its globals:

    say(text)              one line, marked with the pack's name
    show(*lines)           lines as they are, for a table
    status(item)           a block in the Combat tracking panel -- {label, value,
                           note, rows: [[key, text, [bits]]], chips: [[name, n]]}
                           -- or a line of text; "" takes it away
    owner                  its own name, for gags it adds and takes away
    level()                a profession's level, once `profs` has said it
    await fresh_level()    sends `profs` and waits for the answer
    await go_to(place)     walks to a 3kdb speedrun destination; True there
    keep                   a dict kept in the character's folder; keep.save()

3kdb is public domain (the Unlicense), which is what lets its tables of
crafting components, gems and jewels come across with the code.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .. import events
from ..outbound import HIGH, NOW
from ..paths import set_aside, write_atomically
from ..triggers import Trigger

#: A loaded pack's name among the scripts.  No file in the scripts folder can
#: have it -- a colon is not allowed in a Windows file name -- so a player's
#: own `trapper.py` and the Trapper pack never unload each other.
PREFIX = "pack:"

#: What `profs` says first.  3kdb's own pattern, less the TinTin++.
PROFS = r"^Profession #1\s*:\s*(.+?)\s*\(Level\s*(\d+)\)"


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    #: what it does, in a few words, for the character screen
    gives: str
    #: what it adds, as you type it
    commands: tuple[str, ...]
    kind: str = "profession"


PROFESSIONS = (
    Pack("golem_master", "Golem Master",
         "builds a golem a part per corpse, and fills it",
         ("build_golem <kind>", "fill_golem")),
    Pack("herbologist", "Herbologist",
         "what each herb does, and how long it lasted",
         (".herbs",)),
    Pack("marshal", "Marshal",
         "counts the standard's charges; rallycry once a fight if asked",
         (".standard", ".rallycry <kind> on|off")),
    Pack("reforger", "Reforger",
         "reforging shortcuts",
         ("ref <item> <type>", "refg <item> <type>", "refk", "refs",
          "refk1", "refk2")),
    Pack("transmuter", "Transmuter",
         "burns and upgrades what is in the satchel",
         ("transmute_burn <mode>", "transmute_burn2 <quality>",
          "transmute_ug <item> <quality>", "transmute_ratios",
          "transmuter-stats")),
    Pack("trapper", "Trapper",
         "counts traps and materials, scrounges in your order",
         (".traps", ".scrounge <item>", ".scrounge-pref",
          ".scrounge+ <material>", ".scrounge- <material>")),
)

EXTRAS = (
    Pack("corpses", "Corpse counts",
         "where your corpses are, in the Combat tracking panel",
         (".corpses", "corpse_select"), "extra"),
    Pack("crafting", "Crafting helpers",
         "assembling, smelting, the forge, gems and tomes",
         ("assembler", "autosmelt <ore>", "forge-on", "forge-off",
          "fill-moulding", "make-gem <gem>", "gem-lookup <word>",
          "jewel-lookup <word>", "borrow-tomes <i|ii|iii>",
          "buy-tomes <i|ii|iii>", "box-tomes <i|ii|iii>"), "extra"),
    Pack("kills", "Kill stats",
         "every kill's rounds, time, damage, xp and coins, with rates",
         (".kills [count|mob|clear|ask off]", "3kReport", "3kReport-clear"),
         "extra"),
)


def find(wanted, among=PROFESSIONS) -> Pack | None:
    """By id or by name, as `profs` prints it; None for anything else."""
    key = str(wanted or "").strip().lower()
    return next((p for p in among
                 if key in (p.id, p.name.lower())), None) if key else None


def find_extra(wanted) -> Pack | None:
    return find(wanted, EXTRAS)


def extra_ids(wanted) -> list[str]:
    """Only extras this client has, once each, in the catalogue's order."""
    if not isinstance(wanted, (list, tuple)):
        return []
    found = {getattr(find_extra(w), "id", None) for w in wanted}
    return [e.id for e in EXTRAS if e.id in found]


def listing(among=PROFESSIONS) -> list[dict]:
    return [{"id": p.id, "name": p.name, "gives": p.gives,
             "commands": list(p.commands)} for p in among]


def extras_listing() -> list[dict]:
    return listing(EXTRAS)


def source(pid: str) -> str:
    # Read as a resource, like the page: an installed client has no promise
    # of a filesystem path to its own package.
    return (resources.files(__package__).joinpath(f"{pid}.py")
            .read_text(encoding="utf-8"))


class Keep(dict):
    """A pack's settings, in the character's folder.  Saved when asked."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = Path(path) if path is not None else None
        if self.path is None or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("not an object")
            self.update(data)
        except (OSError, ValueError):
            set_aside(self.path)          # kept, not overwritten by the next save

    def save(self) -> None:
        if self.path is not None:
            write_atomically(self.path, json.dumps(self, indent=2))


def _names(host) -> dict:
    return getattr(host, "registries", {}) or {}


def loaded(host) -> Pack | None:
    """The profession loaded, if any."""
    return next((p for p in PROFESSIONS if PREFIX + p.id in _names(host)), None)


def loaded_extras(host) -> list[str]:
    return [e.id for e in EXTRAS if PREFIX + e.id in _names(host)]


def matches(host, char) -> bool:
    """Is what is loaded what this character asks for?"""
    return (loaded(host) == find(getattr(char, "profession", ""))
            and loaded_extras(host) == extra_ids(getattr(char, "extras", [])))


def use(host, pid, folder: Path | None = None) -> Pack | None:
    """Load `pid`'s profession in place of whichever was loaded.  "" loads none."""
    if host is None or not hasattr(host, "load_source"):
        return None
    for prof in PROFESSIONS:
        _unload(host, prof)
    prof = find(pid)
    if prof is None:
        return None
    return prof if _load(host, prof, folder) else None


def use_extras(host, wanted, folder: Path | None = None,
               fresh: bool = True) -> list[str]:
    """Exactly these extras.  One already loaded is kept, counts and all,
    unless `fresh` -- which is what a different character needs."""
    if host is None or not hasattr(host, "load_source"):
        return []
    ids = extra_ids(wanted)
    for extra in EXTRAS:
        if extra.id not in ids or fresh:
            _unload(host, extra)
    for extra in EXTRAS:
        if extra.id in ids and PREFIX + extra.id not in _names(host):
            _load(host, extra, folder)
    return loaded_extras(host)


def apply(host, char, folder: Path | None = None, fresh: bool = True) -> None:
    """A character's profession and extras, and nobody else's."""
    if fresh or loaded(host) != find(getattr(char, "profession", "")):
        use(host, getattr(char, "profession", ""), folder)
    use_extras(host, getattr(char, "extras", []), folder, fresh)


def _unload(host, pack: Pack) -> None:
    name = PREFIX + pack.id
    if name in _names(host):
        host.unload(name)
    lines = host.session.__dict__.get("pack_status", {})
    if lines.pop(name, None) is not None:
        host.session.bus.emit(events.STATE, "pack_status", "", None)


def _load(host, pack: Pack, folder: Path | None) -> bool:
    owner = PREFIX + pack.id
    bus, session = host.session.bus, host.session
    heard = {"level": None, "at": 0.0, "warned": False}

    def show(*lines: str) -> None:
        bus.emit(events.TEXT, ("\r\n" + "\r\n".join(lines) + "\r\n")
                 .encode("latin-1", "replace"))

    def say(text: str) -> None:
        show(f"\x1b[36m[{pack.name}]\x1b[0m {text}")

    def status(text) -> None:
        lines = session.__dict__.setdefault("pack_status", {})
        if text:
            lines[owner] = text
        else:
            lines.pop(owner, None)
        bus.emit(events.STATE, "pack_status", text, None)

    async def fresh_level(timeout: float = 3.0):
        asked = time.monotonic()
        session.queue.put("profs", HIGH, NOW)
        while time.monotonic() - asked < timeout and heard["at"] < asked:
            await asyncio.sleep(0.05)
        return heard["level"]

    async def go_to(place: str, timeout: float = 180.0) -> bool:
        store = getattr(session, "store", None)
        mapper = getattr(session, "mapper", None)
        mark = store.landmark(place) if store is not None else None
        if mark is None or mapper is None:
            say(f"the map has no {place} to walk to.")
            return False
        room = int(mark["room_id"])

        def here():
            at = mapper.here
            return getattr(at, "id", at)

        if here() == room:
            return True
        if mapper.route(room) is None:
            say(f"no way from here to {mark['name']}.")
            return False
        session.travel(room, "speedwalk", mark["name"])
        began = time.monotonic()
        while time.monotonic() - began < timeout:
            await asyncio.sleep(0.25)
            if here() == room:
                return True
        say(f"did not reach {mark['name']}.")
        return False

    extra = {
        "say": say, "show": show, "status": status, "owner": owner,
        "fresh_level": fresh_level, "go_to": go_to,
        "level": lambda: heard["level"],
        "keep": Keep(Path(folder) / f"{pack.id}.json" if folder else None),
    }
    if not host.load_source(owner, source(pack.id), f"<{pack.name}>", extra,
                            builtin=True):
        return False

    if pack.kind == "profession":
        def profs(m) -> None:
            named = m[1].strip()
            if named.lower() == pack.name.lower():
                heard["level"], heard["at"] = int(m[2]), time.monotonic()
            elif not heard["warned"]:
                heard["warned"] = True
                say(f"3K says your first profession is {named}, but this "
                    f"character is set up as a {pack.name}.  Change it with "
                    "Edit on the character screen.")

        host.triggers.add(Trigger(PROFS, profs, "regex", owner))
    say("loaded: " + ", ".join(pack.commands))
    return True
