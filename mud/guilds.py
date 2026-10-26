"""The ``Guild.*`` packages, assembled.

3Scapes sends a great deal about your guild over GMCP -- seven packages on
a gentech, dozens of fields each -- and **the field names are the guild's
own**.  A gentech has `dna`, `hypergen` and `tacshield`; another guild has
nothing of the sort.  Only the package names are shared.

So this does not know, and must not pretend to know, what any field means.
It assembles them -- a payload marked ``full`` replaces, one without it
merges, a paged one is collected -- and hands over what the MUD said, under
the names the MUD used.  A guess at a friendlier label is a guess that can
be wrong, and wrong is worse here than terse: these are the names the
player already reads in the game.

Which is also why there is one of these rather than one per guild.  A panel
per guild would be a panel for the guilds somebody got round to, and this
client would be the one that knows about three of them.
"""

from __future__ import annotations

#: Not rows: these say how to read the payload, not what is in it.
PLUMBING = ("full", "page", "pages")


class GuildFeed:
    """What the Guild.* packages add up to, package by package."""

    def __init__(self) -> None:
        #: package name -> the assembled tree, the MUD's own field names
        self.packages: dict[str, dict] = {}

    def clear(self) -> None:
        """A new character, or a new connection: none of it carries over."""
        self.packages.clear()

    @property
    def guild(self) -> str:
        """Whichever guild the packages say they are about."""
        for body in self.packages.values():
            name = body.get("guild")
            if name:
                return str(name)
        return ""

    def take(self, package: str, body) -> bool:
        """One frame.  True if anything changed, so the screen can be lazy."""
        if not package.startswith("Guild.") or not isinstance(body, dict):
            return False
        # Every package says whose guild it is about, so a different answer
        # means none of what is held belongs to this character any more.
        # Keeping it would show one guild's numbers under another's name
        # until each package happened to change and replace itself.
        said = str(body.get("guild") or "")
        if said and self.guild and said != self.guild:
            self.packages.clear()
        before = self.packages.get(package)
        held = dict(before) if before else {}

        if body.get("pages"):
            # Paged: the pages are one answer sent in instalments, so page
            # one starts a fresh set and the rest add to it.  Shown as they
            # arrive rather than held back -- a page is right the moment it
            # lands, and waiting only means an empty panel for a second.
            if int(body.get("page") or 0) <= 1:
                held = {}
        elif body.get("full"):
            # A whole snapshot: a field it does not carry is a field the
            # MUD has dropped, not one it forgot to mention.
            held = {}

        held.update({k: v for k, v in body.items() if k not in PLUMBING})
        if held == before:
            return False
        self.packages[package] = held
        return True

    def public(self) -> dict:
        """For the browser: the packages that have said anything."""
        return {name: dict(body) for name, body in sorted(self.packages.items())
                if body}
