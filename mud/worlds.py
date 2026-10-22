"""The two MUDs this client plays.

Three Kingdoms and 3Scapes are sister games on the same mudlib, and they are
the only two addresses a character can have.  So the character screen offers
the pair rather than an address box: a box invites an address the client has
never spoken to, and -- until this module existed -- what the box said and
where the client actually connected were two different things.

Every address the client is given goes through :func:`of`, which answers with
one of these two.  Anything else, including an old saved character from before
the choice existed, is Three Kingdoms.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class World:
    #: short, stable, and what the browser sends back
    id: str
    name: str
    host: str
    port: int
    #: what is added to a filename to keep this world's copy apart.  Three
    #: Kingdoms keeps the plain names -- its files were there first, and a
    #: rename would strand the map every installed client already has.
    slug: str = ""
    #: whether 3kdb has a map and a path library for it.  Only 3K does, and
    #: the difference decides both what Updates may fetch and whether the
    #: map starts locked: a world with nothing to import has to be walked.
    has_3kdb: bool = True

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def file(self, path: str | Path) -> Path:
        """This world's copy of a file the other one also has.

        The two games are two geographies.  One map file holding both would
        be a path that walks you out of Three Kingdoms and into 3Scapes.
        """
        p = Path(path)
        if not self.slug or str(path) == ":memory:":
            return p
        return p.with_name(f"{p.stem}-{self.slug}{p.suffix}")

    def base(self, path: str | Path) -> Path:
        """The plain name :meth:`file` made this world's copy from."""
        p = Path(path)
        tail = f"-{self.slug}"
        if self.slug and p.stem.endswith(tail):
            return p.with_name(p.stem[:-len(tail)] + p.suffix)
        return p

    def public(self) -> dict:
        return {"id": self.id, "name": self.name,
                "host": self.host, "port": self.port}


#: The first is the default, and what an address we do not know falls back to.
ALL = (
    World("3k", "Three Kingdoms", "3k.org", 3000),
    World("3s", "3Scapes", "3scapes.org", 3200, slug="3scapes",
          has_3kdb=False),
)
DEFAULT = ALL[0]


def listing() -> list[dict]:
    """The pair, for the character screen."""
    return [w.public() for w in ALL]


def find(host: str = "", port: int | None = None) -> World | None:
    """The world at this address, or by id.  None if it is neither of ours.

    The host decides.  A port on its own is enough to tell them apart, so it
    is tried next -- an old entry with the right port and a host that has
    since moved is still recognisably one of the two.
    """
    key = str(host or "").strip().lower()
    if key:
        # A URL-ish "3k.org:3000" or "//3k.org" is still a host we know.
        key = key.split("//")[-1].split("/")[0].rsplit(":", 1)[0].strip("[]")
        for w in ALL:
            if key in (w.id, w.host, w.name.lower()):
                return w
    try:
        number = int(port)        # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    for w in ALL:
        if number == w.port:
            return w
    return None


def of(host: str = "", port: int | None = None) -> World:
    """Which of the two this address is -- Three Kingdoms if it is neither."""
    return find(host, port) or DEFAULT
