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

import io
import json
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .tintin import import_bots, import_map, import_speedruns

OWNER, REPO, BRANCH = "jmitchell33", "3kdb", "master"

TREE = (f"https://api.github.com/repos/{OWNER}/{REPO}"
        f"/git/trees/{BRANCH}?recursive=1")
#: One request, compressed, rather than a hundred and seventy.  The map alone
#: is 25MB of text and goes over the wire at a fraction of that.
TARBALL = (f"https://codeload.github.com/{OWNER}/{REPO}"
           f"/tar.gz/refs/heads/{BRANCH}")

#: What we take, in the order it is worth having.
WANTED = {
    "map": "common/map/3k_shared.map",
    "speedruns": "common/map/speedruns.tin",
    "bots": "common/bot",
}

AGENT = f"3k-client/{__version__} (+https://github.com/{OWNER}/{REPO})"

#: Refuse a download that is not the size of a repository.  A redirect to a
#: login page is small; something has gone wrong if it is enormous.
MOST = 200 * 1024 * 1024


def _get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": AGENT,
        "Accept-Encoding": "gzip",
    })
    # HTTPS with the default context, which verifies certificates.  Worth
    # saying out loud: this is somebody else's repository over the open
    # internet, and it ends up in the map.
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        body = reply.read(MOST + 1)
        if len(body) > MOST:
            raise ValueError(f"{url}: refusing a reply over {MOST} bytes")
        if reply.headers.get("Content-Encoding") == "gzip":
            import gzip
            body = gzip.decompress(body)
        return body


# --- the client itself -------------------------------------------------------
#
# Separate from everything above, and worth saying why: 3kdb is data this
# client reads, and this is the client.  A new map arrives by pressing a
# button; a new client arrives by downloading an installer and running it,
# which is not something a program should do to itself unasked.

CLIENT = "OldManDanky/dankclient"
RELEASES = f"https://api.github.com/repos/{CLIENT}/releases/latest"


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
        return {"error": f"{type(exc).__name__}: {exc}", "have": mine}
    if found.get("draft") or not found.get("tag_name"):
        return {"error": "", "have": mine, "latest": "", "newer": False}

    tag = str(found["tag_name"])
    installer = next(
        (a["browser_download_url"] for a in found.get("assets", ())
         if str(a.get("name", "")).endswith(".msi")), found.get("html_url", ""))
    return {
        "error": "",
        "have": mine,
        "latest": tag.lstrip("vV"),
        "newer": numbers(tag) > numbers(mine),
        "url": installer,
        "page": found.get("html_url", ""),
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
        return {"error": f"{type(exc).__name__}: {exc}"}

    by_path = {e["path"]: e for e in tree.get("tree", ())}
    out: dict = {"error": "", "items": {}}
    for key, path in WANTED.items():
        entry = by_path.get(path)
        if entry is None:
            out["items"][key] = {"path": path, "there": False}
            continue
        was = have.get(key, "")
        out["items"][key] = {
            "path": path,
            "there": True,
            "sha": entry["sha"],
            "have": was,
            "size": entry.get("size") or 0,
            "changed": entry["sha"] != was,
            "new": not was,
        }
    out["changed"] = [k for k, v in out["items"].items() if v.get("changed")]
    return out


def _unpack(blob: bytes, into: Path) -> Path:
    """Extract the parts we want, and nothing else.

    A tarball off the internet is untrusted input: every member is checked to
    be a plain file living under a path we asked for before anything is
    written, so a name with a `..` in it or an absolute path or a symlink
    cannot put a file where it likes.
    """
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue                    # no directories, links or devices
            # GitHub wraps everything in <repo>-<branch>/.
            parts = Path(member.name).parts
            if len(parts) < 2:
                continue
            inside = "/".join(parts[1:])
            if not any(inside == p or inside.startswith(p + "/")
                       for p in WANTED.values()):
                continue
            target = (into / inside).resolve()
            if not str(target).startswith(str(into.resolve())):
                continue                    # a name that climbs out
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
    return into


def pull(store, routes, want=None, into: Path | None = None,
         timeout: float = 300.0, note=None) -> dict:
    """Fetch 3kdb and merge what was asked for.  Returns what it did.

    `want` is the keys from `check()`; everything by default.  Whatever is
    downloaded, only what is asked for is imported: the map takes a while and
    there is no reason to redo it because a route file moved.
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
        return {"error": f"{type(exc).__name__}: {exc}", "did": {}}

    try:
        if "map" in want and store is not None:
            path = root / WANTED["map"]
            if path.exists():
                said(f"merging the map ({path.stat().st_size // 1024}k)...")
                done["did"]["map"] = import_map(store, path, merge=True)
        if "speedruns" in want and store is not None:
            path = root / WANTED["speedruns"]
            if path.exists():
                added, missing = import_speedruns(store, path)
                done["did"]["speedruns"] = {"added": added,
                                            "missing": len(missing)}
        if "bots" in want and routes is not None:
            done["did"]["bots"] = import_bots(routes, root)
    finally:
        if into is None:
            holding.cleanup()
    return done


def sync(store, routes, want=None, note=None) -> dict:
    """Check, take what has changed, and write down what was taken.

    The order matters at the end: what we imported is recorded only once the
    import worked.  Recording first and failing second is how an update quietly
    never happens again.
    """
    said = note or (lambda _text: None)
    got = check(store)
    if got.get("error"):
        return {"error": got["error"], "did": {}, "items": {}, "changed": []}

    keys = list(want) if want is not None else list(got["changed"])
    if not keys:
        return {"error": "", "did": {}, "items": got["items"],
                "changed": got["changed"], "nothing": True}

    said(f"taking: {', '.join(keys)}")
    done = pull(store, routes, want=keys, note=said)
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


def on_a_thread(store_path, routes_path, want=None, note=None) -> dict:
    """A sync on connections this thread owns, for asyncio.to_thread.

    sqlite3 refuses a connection across threads, and rightly: the file is the
    shared thing here, not the handle.  WAL means whoever else has it open
    reads the new rows straight afterwards.
    """
    from .botstore import RouteStore
    from .store import Store

    class Bare:
        bots = None

    mine = Store(store_path) if store_path else None
    theirs = None
    if routes_path:
        theirs = RouteStore(Bare(), routes_path)
        theirs.load()
    try:
        return sync(mine, theirs, want=want, note=note)
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
        if item.get("sha"):
            store.set_setting(f"3kdb:{key}", item["sha"])
