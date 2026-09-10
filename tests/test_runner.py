"""The test run cleans up after itself.

Tests make temporary folders with mkdtemp, which nothing removes; left alone
they had filled the disk -- 12,950 folders, 37 GB, with tools/regress.py
adding a copy of the map for every capture.  Both now run inside one folder
of their own that goes when they finish.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))


def test_a_test_run_keeps_its_folders_in_one_it_removes():
    import run

    seen = {}

    def body():
        seen["tmp"] = tempfile.gettempdir()
        seen["env"] = os.environ.get("TMPDIR")
        Path(tempfile.mkdtemp(), "leftover").write_text("x")
        return 0

    before = tempfile.tempdir, os.environ.get("TMPDIR")
    assert run.in_scratch(body) == 0
    assert Path(seen["tmp"]).name.startswith("dankclient-tests-")
    assert seen["env"] == seen["tmp"], "anything the run starts uses it too"
    assert not Path(seen["tmp"]).exists(), "and it is gone afterwards"
    assert (tempfile.tempdir, os.environ.get("TMPDIR")) == before


def test_the_replay_cleans_up_too():
    text = (HERE.parent / "tools" / "regress.py").read_text()
    assert "in_scratch(main)" in text
