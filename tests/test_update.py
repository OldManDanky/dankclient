"""Taking 3kdb's map and bot library, without going near the network.

The reading and merging are tested in test_tintin; what is left here is the
part that decides *whether* to take anything, and the part that opens a
tarball somebody else made.
"""

from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import update  # noqa: E402
from mud.store import Store  # noqa: E402


class FakeTree:
    """Stands in for one GitHub API call."""

    def __init__(self, shas: dict):
        self.shas = shas
        self.asked = 0

    def __call__(self, url, timeout):
        self.asked += 1
        return json.dumps({"tree": [
            {"path": path, "sha": sha, "size": 10, "type": "blob"}
            for path, sha in self.shas.items()]}).encode()


def watching() -> dict:
    return {p: f"sha-{k}" for k, p in update.WANTED.items()}


def with_tree(shas, fn):
    was, update._get = update._get, FakeTree(shas)
    try:
        return fn()
    finally:
        update._get = was


def test_everything_is_new_until_it_has_been_taken():
    store = Store()
    got = with_tree(watching(), lambda: update.check(store))
    assert got["error"] == ""
    assert sorted(got["changed"]) == sorted(update.WANTED)
    assert all(v["new"] for v in got["items"].values())


def test_what_was_taken_is_not_offered_again():
    store = Store()
    shas = watching()
    got = with_tree(shas, lambda: update.check(store))
    update.remember(store, got, ["map"])

    again = with_tree(shas, lambda: update.check(store))
    assert again["items"]["map"]["changed"] is False
    assert "map" not in again["changed"]
    assert "bots" in again["changed"], "the others are still outstanding"


def test_a_file_that_moves_is_offered_again():
    """The whole point: 3kdb keeps growing, and one sha covers all hundred and
    seventy route files because `common/bot` is watched as a directory."""
    store = Store()
    shas = watching()
    update.remember(store, with_tree(shas, lambda: update.check(store)),
                    list(update.WANTED))
    assert with_tree(shas, lambda: update.check(store))["changed"] == []

    shas[update.WANTED["bots"]] = "sha-bots-moved"
    assert with_tree(shas, lambda: update.check(store))["changed"] == ["bots"]


def test_one_request_answers_for_all_three():
    store = Store()
    tree = FakeTree(watching())
    was, update._get = update._get, tree
    try:
        update.check(store)
    finally:
        update._get = was
    assert tree.asked == 1


def test_a_path_the_repository_has_dropped_is_reported_not_guessed():
    store = Store()
    shas = watching()
    del shas[update.WANTED["map"]]
    got = with_tree(shas, lambda: update.check(store))
    assert got["items"]["map"]["there"] is False
    assert "map" not in got["changed"]


def test_the_network_going_wrong_is_an_answer_not_a_crash():
    def boom(url, timeout):
        raise OSError("no route to host")

    store = Store()
    was, update._get = update._get, boom
    try:
        got = update.check(store)
    finally:
        update._get = was
    assert "no route to host" in got["error"]
    assert got.get("items", {}) == {}


# --- opening somebody else's tarball -----------------------------------------

def tarball(names: dict) -> bytes:
    """`names` maps a path inside the archive to its bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, body in names.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


def test_only_the_parts_we_asked_for_come_out():
    into = Path(tempfile.mkdtemp()) / "out"
    update._unpack(tarball({
        "3kdb-master/common/map/speedruns.tin": b"runs",
        "3kdb-master/chars/badger/aliases.tin": b"not ours",
        "3kdb-master/README.md": b"no",
    }), into)
    assert (into / "common/map/speedruns.tin").read_bytes() == b"runs"
    assert not (into / "chars").exists()
    assert not (into / "README.md").exists()


def test_a_name_that_climbs_out_is_refused():
    """A tarball off the internet is untrusted input, and tarfile will happily
    write outside the directory you gave it if the names say so."""
    into = Path(tempfile.mkdtemp()) / "out"
    update._unpack(tarball({
        "3kdb-master/../../../../tmp/3k-escaped": b"nope",
        "3kdb-master/common/map/../../../../tmp/3k-escaped-too": b"nope",
    }), into)
    assert not Path("/tmp/3k-escaped").exists()
    assert not Path("/tmp/3k-escaped-too").exists()


def test_a_link_is_not_a_file():
    """Only plain files are taken -- a symlink pointing at ~/.ssh is a way to
    make the next read go somewhere it should not."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("3kdb-master/common/map/speedruns.tin")
        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(info)
    into = Path(tempfile.mkdtemp()) / "out"
    update._unpack(buf.getvalue(), into)
    assert not (into / "common/map/speedruns.tin").exists()


def test_scripts_are_not_on_the_list():
    """They are Python and they hot-reload. Pulling them from the internet
    would be running somebody else's code as you, which is a different kind of
    button from this one."""
    assert not any("script" in path for path in update.WANTED.values())


# --- the first run ------------------------------------------------------------

def test_a_client_with_no_map_has_never_run():
    """Somebody who has just installed this should not have to be told the
    first thing to do is go and find fifty thousand rooms."""
    store = Store()
    assert update.never_run(store) is True
    store.add_room("The Center of Town")
    assert update.never_run(store) is False


def test_a_client_with_no_map_at_all_is_not_a_first_run():
    """--no-map means somebody said no to mapping, not that it is missing."""
    assert update.never_run(None) is False


def test_a_broken_store_does_not_stop_the_client_starting():
    class Wrecked:
        class db:
            @staticmethod
            def execute(*a):
                raise RuntimeError("no such table")
    assert update.never_run(Wrecked()) is False
