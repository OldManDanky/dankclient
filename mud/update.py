"""Pulling 3kdb's map and bot library into this client.

https://github.com/jmitchell33/3kdb is a TinTin++ setup for 3K, and it is
where this map came from: fifty thousand rooms somebody else walked, and a
couple of hundred routes recording which rooms hold which monsters and in what
order to visit them.  It keeps growing, and there is no reason every player
should have to notice by hand.

Three things are watched::

    common/map/3k_shared.map   the map -- 25MB, and the reason for the tarball
    common/map/speedruns.tin   named destinations, which is what /go walks to
    common/bot                 the routes, as a directory: one sha for the lot

All three are data.  Nothing downloaded here is executed -- the map is parsed
into SQLite and the bot files are read with a regex -- which is what makes this
a reasonable thing to have a button for.  `scripts/` is the opposite case and
is deliberately not in the list: those are Python and they hot-reload, so
pulling them from the internet would be running somebody else's code as you.

Nothing is replaced, either.  The map is merged, which only adds; a route you
have edited is left alone.  Both were measured before they were trusted.
"""

from __future__ import annotations

import functools
import io
import json
import re
import ssl
import tarfile
import urllib.error
import urllib.request
import zlib
from importlib import resources
from pathlib import Path, PurePosixPath

from . import SLUG, __version__
from .tintin import import_bots, import_map, import_speedruns

OWNER, REPO, BRANCH = "jmitchell33", "3kdb", "master"

TREE = (f"https://api.github.com/repos/{OWNER}/{REPO}"
        f"/git/trees/{BRANCH}?recursive=1")
#: One request, compressed, rather than a hundred and seventy.  The map alone
#: is 25MB of text and goes over the wire at a fraction of that.
TARBALL = (f"https://codeload.github.com/{OWNER}/{REPO}"
           f"/tar.gz/refs/heads/{BRANCH}")

#: Bump one of these when its importer changes what it would make of the same
#: input.  What we remember is what we took *and how* -- otherwise a parser bug
#: is frozen in place by the very record that says we already have this, and
#: the fix reaches nobody who had already pulled.  Reading `.add_bot` lines
#: with six fields as well as seven took the route library from 67 to 141.
#: The map went to 2 when rooms with no name stopped being thrown away and
#: tt++'s void spacers were walked through: 3,478 dropped rooms had been the
#: only ways into whole areas -- Xenolocles by way of Ravenloft, Westersea,
#: the Underdark -- and a quarter of the speedruns could not be reached.
IMPORTERS = {"map": 2, "speedruns": 1, "bots": 2, "gags": 1}

#: What we take, in the order it is worth having.
WANTED = {
    "map": "common/map/3k_shared.map",
    "speedruns": "common/map/speedruns.tin",
    "bots": "common/bot",
    #: taken, but every group off until somebody switches it on
    "gags": "common/gags",
}

AGENT = f"{SLUG}/{__version__} (+https://github.com/OldManDanky/dankclient)"

#: Refuse a download that is not the size of a repository.  A redirect to a
#: login page is small; something has gone wrong if it is enormous.
MOST = 200 * 1024 * 1024
#: ...and the same once it is opened.  A tarball is compressed, and a small
#: download that unpacks into gigabytes is the whole trick of an archive bomb.
MOST_UNPACKED = 400 * 1024 * 1024


@functools.lru_cache(maxsize=1)
def _trust() -> ssl.SSLContext:
    """What HTTPS is checked against: this machine's store, and Mozilla's list.

    The machine's store alone was not enough.  On Windows it is filled in on
    demand -- a root arrives the first time a Windows program asks for it,
    and Python reading the store is not asking -- so a machine that had never
    opened GitHub in a browser failed every request with "unable to get local
    issuer certificate".  A tester's client came up with no map, no bots and
    that error on the Updates page.

    Mozilla's list, as curl publishes it, is carried in the package and
    trusted *alongside* the store rather than instead of it: a work proxy or
    an antivirus that re-signs HTTPS puts its own root in the store, and that
    has to go on working.  Nothing is loosened -- certificates and host names
    are checked exactly as before, against more roots.
    """
    context = ssl.create_default_context()
    try:
        text = (resources.files(__package__ or "mud")
                / "cacert.pem").read_text(encoding="ascii")
        blocks = re.findall(r"-----BEGIN CERTIFICATE-----\s.*?"
                            r"-----END CERTIFICATE-----", text, re.S)
        if blocks:
            context.load_verify_locations(cadata="\n".join(blocks) + "\n")
    except (OSError, ValueError, ssl.SSLError):
        pass                        # the machine's own store still stands
    return context


def _say(exc: BaseException) -> str:
    """A failure as somebody could act on it, with the detail kept."""
    text = f"{type(exc).__name__}: {exc}"
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return ("could not verify GitHub's certificate. If this computer's "
                "clock is wrong, set it right; a work proxy or antivirus that "
                "scans HTTPS can also cause this. (" + text + ")")
    return text


def _get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": AGENT,
        "Accept-Encoding": "gzip",
    })
    # HTTPS, verified -- see _trust() for against what.  Worth saying out
    # loud: this is somebody else's repository over the open internet, and
    # it ends up in the map.
    with urllib.request.urlopen(request, timeout=timeout,
                                context=_trust()) as reply:
        body = reply.read(MOST + 1)
        if len(body) > MOST:
            raise ValueError(f"{url}: refusing a reply over {MOST} bytes")
        if reply.headers.get("Content-Encoding") == "gzip":
            # Opened with a ceiling, for the same reason as the download.
            opener = zlib.decompressobj(wbits=31)
            body = opener.decompress(body, MOST + 1)
            if len(body) > MOST or opener.unconsumed_tail:
                raise ValueError(f"{url}: refusing a reply over {MOST} "
                                 f"bytes unpacked")
        return body


# --- the client itself -------------------------------------------------------
#
# Separate from everything above, and worth saying why: 3kdb is data this
# client reads, and this is the client.  A new map arrives by pressing a
# button; a new client arrives by downloading an installer and running it,
# which is not something a program should do to itself unasked.

CLIENT = "OldManDanky/dankclient"
RELEASES = f"https://api.github.com/repos/{CLIENT}/releases/latest"


def _on_github(url) -> str:
    """The address if it is a page on GitHub, and nothing otherwise.

    It becomes a link somebody is invited to click, so it is not taken on
    trust from a reply: a `javascript:` address there would be a script
    running inside the client's own page, which is the one place that can
    drive the character.
    """
    url = str(url or "")
    return url if url.startswith("https://github.com/") else ""


def numbers(tag: str) -> tuple:
    """A version as something comparable.  "v0.2.0" and "0.2.0" are the same.

    Anything after the digits is dropped, so 0.2.0-beta sorts as 0.2.0 rather
    than raising.  A tag nobody can parse compares as older than everything,
    which is the safe direction: it will not claim an update exists.
    """
    out = []
    for part in str(tag).lstrip("vV").split("."):
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def newer_release(timeout: float = 15.0, have: str = "") -> dict:
    """Is there a newer client than this one?  One request, and no download.

    Being told is the whole feature.  Fetching and running an installer on
    somebody's behalf is a different thing entirely, and not one a MUD client
    should be doing while they are playing.
    """
    mine = have or __version__
    try:
        found = json.loads(_get(RELEASES, timeout))
    except (urllib.error.URLError, ValueError, OSError,
            json.JSONDecodeError) as exc:
        return {"error": _say(exc), "have": mine}
    if found.get("draft") or not found.get("tag_name"):
        return {"error": "", "have": mine, "latest": "", "newer": False}

    tag = str(found["tag_name"])
    installer = next(
        (a.get("browser_download_url") for a in found.get("assets", ())
         if str(a.get("name", "")).endswith(".msi")), found.get("html_url", ""))
    return {
        "error": "",
        "have": mine,
        "latest": tag.lstrip("vV"),
        "newer": numbers(tag) > numbers(mine),
        "url": _on_github(installer),
        "page": _on_github(found.get("html_url")),
        "name": found.get("name") or tag,
        "when": (found.get("published_at") or "")[:10],
    }


def taken(store) -> dict:
    """What we last took, by key.  Read where the store is safe to read."""
    if store is None:
        return {}
    return {key: store.setting(f"3kdb:{key}", "") for key in WANTED}


def check(store, timeout: float = 20.0, have: dict | None = None) -> dict:
    """What 3kdb has, against what we last took from it.

    One request.  The tree gives a sha for every path in the repository,
    including `common/bot` as a directory -- so a single value says whether any
    of the hundred and seventy route files has changed.

    `have` is there because this is worth running off the main thread and a
    sqlite3 connection belongs to the thread that made it.  Read the settings
    where the store lives, and hand them in.
    """
    if have is None:
        have = taken(store)
    try:
        tree = json.loads(_get(TREE, timeout))
    except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as exc:
        return {"error": _say(exc)}

    by_path = {e["path"]: e for e in tree.get("tree", ())}
    out: dict = {"error": "", "items": {}}
    for key, path in WANTED.items():
        entry = by_path.get(path)
        if entry is None:
            out["items"][key] = {"path": path, "there": False}
            continue
        was = have.get(key, "")
        # sha and importer together: either moving is a reason to take it.
        mark = f"{entry['sha']}/{IMPORTERS.get(key, 1)}" if entry else ""
        out["items"][key] = {
            "path": path,
            "there": True,
            "sha": entry["sha"],
            "have": was,
            "size": entry.get("size") or 0,
            "changed": mark != was,
            "new": not was,
            "mark": mark,
        }
    out["changed"] = [k for k, v in out["items"].items() if v.get("changed")]
    return out


def _unpack(blob: bytes, into: Path) -> Path:
    """Extract the parts we want, and nothing else.

    A tarball off the internet is untrusted input: every member is checked to
    be a plain file living under a path we asked for before anything is
    written, so a name with a `..` in it or an absolute path or a symlink
    cannot put a file where it likes.

    Checked as a name first and as a place second.  The place alone was
    checked with startswith(), and `common/bot/../../../out2/f` passed it:
    unpacking into `.../out`, the path `.../out2/f` starts with `.../out`.
    Names are read as tar writes them, with forward slashes -- a backslash
    or a colon means something else again on Windows, so neither is allowed.
    """
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue                    # no directories, links or devices
            name = PurePosixPath(member.name)
            parts = name.parts
            if (name.is_absolute() or len(parts) < 2
                    or any(p == ".." or "\\" in p or ":" in p for p in parts)):
                continue                    # a name that climbs, or means more
            # GitHub wraps everything in <repo>-<branch>/.
            inside = "/".join(parts[1:])
            if not any(inside == p or inside.startswith(p + "/")
                       for p in WANTED.values()):
                continue
            total += member.size
            if member.size > MOST or total > MOST_UNPACKED:
                raise ValueError(f"refusing to unpack more than "
                                 f"{MOST_UNPACKED} bytes ({member.name})")
            target = (root / inside).resolve()
            if not target.is_relative_to(root):
                continue                    # a name that climbs out anyway
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
    return into


def _drop_map(store) -> list[tuple[int, int]]:
    """Empty the map, and hand back the log's filing so it can be put back.

    Deleting a room sets its logged lines' room to NULL on the way out, and
    28,824 of them were filed under one here.  3kdb's room numbers are this
    map's room ids, so a line filed under room 4213 belongs under room 4213
    again the moment the map is back -- but nothing puts it there by itself.
    """
    db = store.db
    filed = [(int(r["id"]), int(r["room_id"])) for r in db.execute(
        "SELECT id, room_id FROM line WHERE room_id IS NOT NULL")]
    db.execute("BEGIN IMMEDIATE")
    try:
        # Exits, fingerprints, marks and landmarks all hang off room and go
        # with it; regions are not reachable from a room and are not cascaded.
        db.execute("DELETE FROM room")
        db.execute("DELETE FROM region")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return filed


def _refile(store, filed: list[tuple[int, int]]) -> int:
    """Put the log's filing back, for the rooms the new map still has.

    A line whose room is not in the map any more keeps no room, and that is
    the right answer: it was filed under a room an older client invented
    while walking, which is one of the reasons to be taking a fresh copy.
    """
    db = store.db
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany(
            "UPDATE line SET room_id = ? WHERE id = ? AND EXISTS "
            "(SELECT 1 FROM room WHERE room.id = ?)",
            [(room, line, room) for line, room in filed])
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return int(db.execute("SELECT COUNT(*) c FROM line "
                          "WHERE room_id IS NOT NULL").fetchone()["c"])


def _drop_routes(routes, root: Path) -> int:
    """Remove the routes 3kdb's own listing names, so they come back as 3kdb
    has them.  A route of your own that it does not name is left alone."""
    listing = Path(root) / "common" / "bot" / "bots.tin"
    if not listing.exists():
        return 0
    from .tintin import read_add_bot
    theirs = set()
    for line in listing.read_text(encoding="latin-1").splitlines():
        got = read_add_bot(line)
        if got is not None:
            theirs.add(got["alias"] or got["file"])
    gone = [r.id for r in routes.routes if r.name in theirs]
    for route_id in gone:
        routes.delete(route_id)
    return len(gone)


def pull(store, routes, want=None, into: Path | None = None,
         timeout: float = 300.0, note=None, fresh: bool = False) -> dict:
    """Fetch 3kdb and merge what was asked for.  Returns what it did.

    `want` is the keys from `check()`; everything by default.  Whatever is
    downloaded, only what is asked for is imported: the map takes a while and
    there is no reason to redo it because a route file moved.

    `fresh` throws this client's copy away first and takes 3kdb's as it
    stands, rather than merging on top.  An ordinary update only ever adds,
    which is right for an update and cannot fix anything that is already
    wrong: an importer that has been corrected since, or rooms an older
    client invented while the map could still grow.  What that costs is on
    the panel before it runs.  Note the order -- nothing is dropped until the
    download has succeeded, so a fresh copy cannot leave you with neither.
    """
    said = note or (lambda _text: None)
    want = set(want if want is not None else WANTED)
    done: dict = {"error": "", "did": {}}

    import tempfile
    holding = tempfile.TemporaryDirectory(prefix="3kdb-")
    root = Path(into) if into is not None else Path(holding.name)
    try:
        said("fetching 3kdb...")
        _unpack(_get(TARBALL, timeout), root)
    except (urllib.error.URLError, tarfile.TarError, ValueError, OSError) as exc:
        holding.cleanup()
        return {"error": _say(exc), "did": {}}

    try:
        if "map" in want and store is not None:
            path = root / WANTED["map"]
            if path.exists():
                filed = None
                if fresh:
                    said("dropping this client's copy of the map...")
                    filed = _drop_map(store)
                said(f"{'rebuilding' if fresh else 'merging'} the map "
                     f"({path.stat().st_size // 1024}k)...")
                got = import_map(store, path, merge=not fresh)
                if filed is not None:
                    got["refiled"] = _refile(store, filed)
                    got["unfiled"] = len(filed) - got["refiled"]
                done["did"]["map"] = got
        if "speedruns" in want and store is not None:
            path = root / WANTED["speedruns"]
            if path.exists():
                if fresh:
                    # Every landmark came from this file; a dropped map has
                    # taken them with it already, and this is for when it was
                    # not asked for.
                    store.db.execute("DELETE FROM landmark")
                added, missing = import_speedruns(store, path)
                done["did"]["speedruns"] = {"added": added,
                                            "missing": len(missing)}
        if "bots" in want and routes is not None:
            dropped = _drop_routes(routes, root) if fresh else 0
            done["did"]["bots"] = import_bots(routes, root)
            done["did"]["bots"]["dropped"] = dropped
        if "gags" in want and routes is not None:
            from .gaglib import LIBRARY, import_gags
            done["did"]["gags"] = import_gags(
                root, Path(routes.path).with_name(LIBRARY))
    finally:
        if into is None:
            holding.cleanup()
    return done


def sync(store, routes, want=None, note=None, fresh: bool = False) -> dict:
    """Check, take what has changed, and write down what was taken.

    The order matters at the end: what we imported is recorded only once the
    import worked.  Recording first and failing second is how an update quietly
    never happens again.

    `fresh` takes 3kdb's copy over this client's rather than merging on top,
    and is asked for by name: a fresh copy of something already up to date is
    the whole point of it, so "nothing has changed" is not a reason to stop.
    """
    said = note or (lambda _text: None)
    got = check(store)
    if got.get("error"):
        return {"error": got["error"], "did": {}, "items": {}, "changed": []}

    keys = list(want) if want is not None else list(got["changed"])
    if fresh:
        # Only what is actually in the repository: a fresh copy of something
        # that is not there would drop the copy we have and put nothing back.
        keys = [k for k in keys if got["items"].get(k, {}).get("there")]
    if not keys:
        return {"error": "", "did": {}, "items": got["items"],
                "changed": got["changed"], "nothing": True}

    said(f"{'taking a fresh copy of' if fresh else 'taking'}: {', '.join(keys)}")
    done = pull(store, routes, want=keys, note=said, fresh=fresh)
    if done.get("error"):
        return {"error": done["error"], "did": {}, "items": got["items"],
                "changed": got["changed"]}

    remember(store, got, [k for k in keys if k in done["did"]])
    # Ask again rather than assuming: taking the bots leaves the map still
    # waiting, and a panel that says "nothing left" after a partial update is
    # a panel that hides the rest of the work.
    after = check(store)
    return {"error": "", "did": done["did"],
            "items": after.get("items", got["items"]),
            "changed": after.get("changed", []), "nothing": False}


def never_run(store) -> bool:
    """Is this a client that has never had a map?

    A fresh install has an empty database and no routes, and a player who has
    just double-clicked an installer should not have to be told that the first
    thing to do is go and find fifty thousand rooms.
    """
    if store is None:
        return False
    try:
        rooms = store.db.execute("SELECT count(*) FROM room").fetchone()[0]
    except Exception:
        return False
    return not rooms


def on_a_thread(store_path, routes_path, want=None, note=None,
                fresh: bool = False) -> dict:
    """A sync on connections this thread owns, for asyncio.to_thread.

    sqlite3 refuses a connection across threads, and rightly: the file is the
    shared thing here, not the handle.  WAL means whoever else has it open
    reads the new rows straight afterwards.
    """
    from .botstore import RouteStore
    from .store import Store

    class Bare:
        bots = None

    # Off the loop, so it can afford to wait for the session's writes.
    mine = Store(store_path, wait=60.0) if store_path else None
    theirs = None
    if routes_path:
        theirs = RouteStore(Bare(), routes_path)
        theirs.load()
    try:
        return sync(mine, theirs, want=want, note=note, fresh=fresh)
    finally:
        if mine is not None:
            mine.close()


def remember(store, got: dict, keys) -> None:
    """Write down what we imported, so the next check knows what is new.

    Only after the import worked.  Recording it first and failing second is how
    an update quietly never happens again.
    """
    if store is None:
        return
    for key in keys:
        item = (got.get("items") or {}).get(key) or {}
        if item.get("mark"):
            store.set_setting(f"3kdb:{key}", item["mark"])
