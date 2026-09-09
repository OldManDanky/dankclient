"""Where the client keeps its things.

Everything used to be relative to the working directory, which is fine while
the only way to run it is `python3 -m mud` from the checkout and wrong the
moment it is installed: a command you can type anywhere would otherwise
scatter a map, a profile directory and a pile of captures into whatever
directory you happened to be standing in.
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud import SLUG  # noqa: E402
from mud.__main__ import build_parser, home  # noqa: E402


@contextmanager
def at(tmp: Path, **env):
    """Stand in `tmp` with these environment variables and no others."""
    was, saved = Path.cwd(), {}
    for key in ("DANK_HOME", "THREEK_HOME", "XDG_DATA_HOME", "LOCALAPPDATA"):
        saved[key] = os.environ.pop(key, None)
    os.environ.update({k: v for k, v in env.items() if v is not None})
    os.chdir(tmp)
    try:
        yield
    finally:
        os.chdir(was)
        for key in ("DANK_HOME", "THREEK_HOME", "XDG_DATA_HOME",
                    "LOCALAPPDATA"):
            os.environ.pop(key, None)
            if saved[key] is not None:
                os.environ[key] = saved[key]


def temp() -> Path:
    import tempfile
    return Path(tempfile.mkdtemp())


def test_a_map_beside_you_wins():
    """A checkout that already has one keeps working exactly as it did --
    nobody's fifty thousand rooms move because the client learned to install."""
    tmp = temp()
    (tmp / "map.sqlite").write_bytes(b"")
    with at(tmp):
        assert home() == Path(".")
        assert build_parser().parse_args([]).map == "map.sqlite"


def test_otherwise_it_is_the_users_own_data_directory():
    tmp = temp()
    with at(tmp, XDG_DATA_HOME="/somewhere/share"):
        assert home() == Path("/somewhere/share") / SLUG


def test_there_is_a_way_to_say_where():
    tmp = temp()
    with at(tmp, DANK_HOME="/opt/dank"):
        assert home() == Path("/opt/dank")


def test_saying_where_beats_the_default_but_not_a_map_beside_you():
    tmp = temp()
    (tmp / "map.sqlite").write_bytes(b"")
    with at(tmp, DANK_HOME="/opt/dank"):
        # Standing in a directory that is plainly a client's is the strongest
        # statement of intent there is.
        assert home() == Path(".")


def test_the_defaults_are_all_under_it():
    """One directory, not four scattered ones: a client you can delete."""
    tmp = temp()
    with at(tmp, DANK_HOME=str(tmp / "here")):
        args = build_parser().parse_args([])
    for got in (args.map, args.profiles, args.scripts):
        assert got.startswith(str(tmp / "here")), got


def test_windows_keeps_its_data_out_of_program_files():
    """An installer puts the program somewhere the user it installed for
    cannot write to, and the map, the profiles and the captures are all things
    the client writes."""
    import mud.__main__ as m

    tmp = temp()
    was = m.sys.platform
    try:
        m.sys.platform = "win32"
        with at(tmp, LOCALAPPDATA=r"C:\Users\someone\AppData\Local"):
            assert home() == Path(r"C:\Users\someone\AppData\Local") / SLUG
    finally:
        m.sys.platform = was


def test_the_help_says_where_they_actually_are():
    """It used to say "default: map.sqlite" whatever the default was."""
    tmp = temp()
    with at(tmp, DANK_HOME="/opt/dank"):
        text = build_parser().format_help()
    assert "/opt/dank" in text


# --- what ships ---------------------------------------------------------------

def test_the_windows_build_carries_the_whole_interface():
    """The build copies the package; a rule that skipped a file type would
    ship a client whose pages half load, and nothing in Python would fail."""
    import tools.build_windows as build  # noqa: E402

    root = Path(__file__).resolve().parents[1]
    shipped = set()
    for path in (root / "mud").rglob("*"):
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_file():
            shipped.add(path.relative_to(root).as_posix())

    for needed in ("mud/ui/index.html", "mud/ui/app.js",
                   "mud/ui/vendor/xterm.js", "mud/ui/vendor/xterm.css",
                   "mud/ui/vendor/LICENSE-xterm"):
        assert needed in shipped, needed
    # every browser file the page asks for
    page = (root / "mud" / "ui" / "index.html").read_text()
    for name in re.findall(r'<script src="([\w./-]+)"', page):
        assert f"mud/ui/{name}" in shipped, name
    assert build.EMBED_SHA, "the interpreter must be pinned by hash"


def test_the_interpreter_is_pinned_by_hash():
    """A build that quietly picks up a different interpreter is a build whose
    bugs cannot be reproduced."""
    import tools.build_windows as build

    assert build.PYTHON in build.EMBED
    assert len(build.EMBED_SHA) == 64
    assert build.EMBED.startswith("https://www.python.org/")


def test_the_bundled_interpreter_can_see_the_client():
    """The embeddable distribution reads its whole sys.path from a ._pth file.
    Without ".." on it, `-m mud` in the folder above is invisible and the
    client cannot start at all."""
    import tools.build_windows as build

    lines = build.PTH.split()
    assert ".." in lines, build.PTH
    assert any(line.endswith(".zip") for line in lines)


def test_nothing_of_yours_goes_into_the_build():
    """The build copies the client, not the player. A map with fifty thousand
    walked rooms, a characters.json that may hold a password, the session
    captures and the routes and triggers you have written are all data, and
    none of it belongs in something handed to somebody else."""
    import tools.build_windows as build

    root = Path(__file__).resolve().parents[1]
    copied = set()
    for path in (root / "mud").rglob("*"):
        if path.is_file():
            copied.add(path.name)

    for private in ("map.sqlite", "characters.json", "routes.json",
                    "rules.json", "prefixes.json"):
        assert private not in copied, private
    # and the build only ever looks inside the package
    source = (root / "tools" / "build_windows.py").read_text()
    assert 'HERE / "mud"' in source
    for outside in ('"profiles"', '"captures"', '"scripts"', '"map.sqlite"'):
        assert outside not in source, f"the build reaches for {outside}"
    assert build.copy_package.__doc__


def test_colour_is_dropped_when_it_would_be_printed_rather_than_shown():
    """Windows consoles do not interpret escape codes unless asked, and every
    line the client printed about itself arrived with a literal "<-[2m" in
    front of it. Redirected output is the same question: a log file full of
    escape codes is a log file nobody can read."""
    import mud.__main__ as m

    was = (m.DIM, m.RESET)
    try:
        m.plain()
        assert m.DIM == "" and m.RESET == "" and m.RED == ""
    finally:
        m.DIM, m.RESET = was

    # Not a terminal here, so it must say so rather than guessing.
    assert m.colour_works() is False


def test_the_app_window_is_its_own_program():
    """Without a profile of its own it joins the browser the player already
    has open: their extensions run against it, and closing it closes nothing,
    because the process was already running. With one it can be waited on, and
    that is the difference between an app and a page."""
    from mud.window import flags

    got = flags("http://127.0.0.1:8081/", Path("/somewhere/profile"))
    assert got[0] == "--app=http://127.0.0.1:8081/"
    assert any(f.startswith("--user-data-dir=") for f in got)


def test_the_launcher_opens_a_window_not_a_browser_tab():
    import tools.build_windows as build

    assert "--app" in build.LAUNCHER
    assert "pythonw.exe" in build.LAUNCHER, "no console behind an app"
    # ...and the fallback keeps its console, because a window that fails to
    # appear has nowhere else to say why.
    assert "python.exe" in build.SILENT and "pause" in build.SILENT
    assert "--app" in build.SILENT


def test_a_machine_with_no_chromium_still_starts():
    """Failing to show somebody a window is not a reason not to run."""
    import mud.window as window

    was, window.find = window.find, lambda: None
    try:
        said = []
        import asyncio
        got = asyncio.run(window.open_window("http://x/", Path("/tmp/nope"),
                                             said.append))
        assert got is None
        assert said and "browser" in said[0]
    finally:
        window.find = was


def test_renaming_the_application_does_not_lose_anybody_a_map():
    """An installation that predates the name keeps its data. Fifty thousand
    rooms is not something to throw away over a rebrand."""
    tmp = temp()
    old = tmp / "3k"
    old.mkdir()
    (old / "map.sqlite").write_bytes(b"")
    with at(temp(), XDG_DATA_HOME=str(tmp)):
        assert home() == old
    # ...but once the new one exists, that is the one.
    (tmp / SLUG).mkdir()
    with at(temp(), XDG_DATA_HOME=str(tmp)):
        assert home() == tmp / SLUG
