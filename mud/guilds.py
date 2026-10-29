"""The ``Guild.*`` packages, assembled.

3Scapes sends a great deal about your guild over GMCP -- seven packages on
a gentech, dozens of fields each -- and **the field names are the guild's
own**.  A gentech has `dna`, `hypergen` and `tacshield`; another guild has
nothing of the sort.  Only the package names are shared.

So this does not know, and must not pretend to know, what any field means.
It assembles them -- the first push of a package replaces what is held and
every push after it merges, which is the rule the guild's own `vhelp gmcp`
states -- and hands over what the MUD said, under the names the MUD used.  A guess at a friendlier label is a guess that can
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
        #: package name -> the paged run in progress, so a list that
        #: continues on the next page is added to rather than replaced
        self._runs: dict[str, dict] = {}

    def clear(self) -> None:
        """A new character, or a new connection: none of it carries over."""
        self.packages.clear()
        self._runs.clear()

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
            self._runs.clear()
        before = self.packages.get(package)
        held = dict(before) if before else {}

        # The guild's own `vhelp gmcp` states the rule, and it is not the one
        # the flags suggest.  `full: 1` comes on the FIRST push of a package
        # after you subscribe, log in or reconnect, and carries every key.
        # Everything after it is only the keys that changed: "merge them into
        # what you hold, never replace it."  So a push without `full` must
        # never clear anything.
        #
        # Paging is reassembly and nothing more.  A push too big for one frame
        # is split, and **every page of a full push carries `full: 1` as well**
        # -- which is the trap: read page two as a snapshot of its own and it
        # throws page one away.  One guild's `Guild.Map` sends the territory's
        # terrain and its two edge grids that way, so the whole map is exactly
        # the thing that gets lost.  A delta can be paged too, and clearing on
        # its first page would wipe the package just as badly.
        #
        # Hence: clear only where both say so -- a full push, at its first
        # page.  Pages are merged as they land rather than held back until the
        # set completes; a page is right the moment it arrives, waiting only
        # means an empty panel for a second, and a page that never comes would
        # otherwise strand the ones that did.
        page = int(body.get("page") or 1)
        pages = int(body.get("pages") or 1)
        if body.get("full") and page <= 1:
            held = {}

        # And a list that does not fit on one page CONTINUES on the next:
        # "page 1 entries first, then page 2".  So a list arriving on a
        # later page is added to the one being built, not put in its place.
        # A thirty-five row map comes over twenty-five pages about four rows
        # at a time; replacing meant holding the last four and drawing a
        # seventh of the territory under a heading that said 70x35.
        #
        # Only ever within an unbroken run from page one of the same set.
        # A page two whose page one we never saw is not a continuation of
        # anything, and appending it to whatever is held would quietly
        # double the map instead of losing most of it -- which is worse,
        # because it looks right.
        run = self._runs.get(package)
        run_on = (pages > 1 and page > 1 and run is not None
                  and run["pages"] == pages and run["page"] == page - 1)

        for key, value in body.items():
            if key in PLUMBING:
                continue
            if (run_on and key in run["keys"]
                    and isinstance(value, list)
                    and isinstance(held.get(key), list)):
                held[key] = held[key] + value
            else:
                held[key] = value

        if pages > 1 and page < pages:
            seen = set(run["keys"]) if run_on else set()
            seen.update(k for k in body if k not in PLUMBING)
            self._runs[package] = {"page": page, "pages": pages, "keys": seen}
        else:
            self._runs.pop(package, None)
        if held == before:
            return False
        self.packages[package] = held
        return True

    def public(self) -> dict:
        """For the browser: the packages that have said anything."""
        return {name: dict(body) for name, body in sorted(self.packages.items())
                if body}
