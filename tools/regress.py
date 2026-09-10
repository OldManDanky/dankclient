"""Replay every capture on disk, and fail if anything got worse.

    python3 tools/regress.py                 compare with the saved baseline
    python3 tools/regress.py --save          make this code the baseline
    python3 tools/regress.py --code DIR      run another checkout's mud/

Green unit tests have never been the evidence here.  Everything that went wrong
in the mapper was found by replaying what 3K actually sent, and this is that
replay made permanent: every capture through the real Session and Mapper, on a
fresh copy of the map, with the clock taken from the capture itself.

Three things are checked:

* **Where the mapper put you, against 3K's own title for that room.**  Scored
  with one yardstick for old and new -- the titles this code reads, which are
  all of them -- because comparing "lost" counts misled twice.  A room placed
  right in the baseline and wrong now fails the run.
* **No marked room title is swallowed.**  A quarter of them once were.
* **A gag that matches nothing changes nothing**, byte for byte.

Captures and the baseline live in captures/, which is never committed: they
hold other people's conversations.  Make the baseline from the last release
before changing the mapper -- a git worktree of the tag and --code -- then run
this after.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import re
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CAPTURES = HERE / "captures"
BASELINE = CAPTURES / "regress-baseline.json"
MAP = HERE / "map.sqlite"


class Wire:
    def write(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


def replay_rooms(clock: list) -> dict:
    """Every capture through Session + Mapper: [[exits, title, placed], ...]."""
    from mud import events
    from mud.capture import replay
    from mud.session import Session
    from mud.store import Store

    src = sqlite3.connect(f"file:{MAP}?mode=ro", uri=True)
    out: dict = {}
    for path in sorted(glob.glob(str(CAPTURES / "*.bin"))):
        stem = path[:-4]
        blob = Path(path).read_bytes()
        sec = re.search(rb"#K%(\d{5})", blob)
        copy = Path(tempfile.mkdtemp()) / "map.sqlite"
        dst = sqlite3.connect(copy)
        src.backup(dst)
        dst.close()
        s = Session(sec_code=int(sec.group(1)) if sec else 12345, jumpstart=False,
                    store=Store(copy), prefixes_path=str(copy.parent / "p.json"))
        s._writer, s.connected = Wire(), True
        taken = [""]
        original = s.markup.take

        def take(exits, original=original, taken=taken):
            got = original(exits)
            taken[0] = got[0]
            return got

        s.markup.take = take
        rows: list = []
        s.bus.on(events.ROOM, lambda room, rows=rows: rows.append([sorted(room.exits)]))
        try:
            for kind, ts, payload in replay(stem):
                clock[0] = ts
                if kind == "sent":
                    text = payload if isinstance(payload, str) else payload.decode("latin-1")
                    s.mapper.sent(text, ts)
                    continue
                n = len(rows)
                s._consume(payload if isinstance(payload, bytes) else payload.encode("latin-1"))
                here = s.mapper.here
                name = ((s.store.db.execute("SELECT name FROM room WHERE id = ?",
                                            (here,)).fetchone() or ["?"])[0]
                        if here else "(lost)")
                for row in rows[n:]:
                    row += [taken[0], name]
            clock[0] += 5
            if hasattr(s, "_room_from_title"):
                s._room_from_title()
        except Exception as exc:                       # report, do not stop
            rows.append(["ERROR", repr(exc)[:100], ""])
        s.store.close()
        out[Path(stem).name] = [r for r in rows if len(r) >= 3]
    return out


def swallowed_titles() -> tuple[int, int]:
    """Marked title lines in the captures, and how many the reader never saw."""
    from mud.lines import strip_ansi
    from mud.markup import Markup

    total = read = 0
    for path in sorted(glob.glob(str(CAPTURES / "*.bin"))):
        text = strip_ansi(Path(path).read_bytes().decode("latin-1"))
        text = re.sub(r"#K%\d{5}\d{3}", "", text)
        markup = Markup()
        for line in (l.rstrip("\r") for l in text.split("\n")):
            got = markup.feed(line)
            if line.startswith("-R-_"):
                total += 1
                read += bool(got)
    return total, total - read


def gag_changes_nothing(clock: list) -> list[str]:
    """Captures whose screen output changes under a gag that matches nothing."""
    from mud import events
    from mud.session import Session
    from mud.triggers import Trigger

    def screen(blob: bytes, gag: bool) -> bytes:
        sec = re.search(rb"#K%(\d{5})", blob)
        s = Session(sec_code=int(sec.group(1)) if sec else 12345, jumpstart=False,
                    prefixes_path=str(Path(tempfile.mkdtemp()) / "p.json"))
        s._writer = Wire()
        if gag and hasattr(s, "gags"):
            s.gags.add(Trigger("zzqq-matches-nothing", lambda m: None, "contains", "regress"))
        out: list[bytes] = []
        s.bus.on(events.TEXT, out.append)
        for i in range(0, len(blob), 1500):
            s._consume(blob[i:i + 1500])
        if hasattr(s, "_let_go"):
            s._let_go()
        return b"".join(out)

    changed = []
    for path in sorted(glob.glob(str(CAPTURES / "*.bin"))):
        blob = Path(path).read_bytes()
        if screen(blob, False) != screen(blob, True):
            changed.append(Path(path).name)
    return changed


def score(before: dict, after: dict) -> tuple[Counter, list]:
    """Line the two runs up by exits; score both against the new titles."""
    tally: Counter = Counter()
    worse: list = []
    for cap in sorted(set(before) | set(after)):
        x, y = before.get(cap), after.get(cap, [])
        if x is None:
            tally["rooms in captures newer than the baseline"] += len(y)
            continue
        ops = difflib.SequenceMatcher(None, [json.dumps(r[0]) for r in x],
                                      [json.dumps(r[0]) for r in y],
                                      autojunk=False).get_opcodes()
        for op, i1, i2, j1, j2 in ops:
            if op == "equal":
                for rx, ry in zip(x[i1:i2], y[j1:j2]):
                    truth = ry[1]
                    if not truth:
                        tally["no title to check against"] += 1
                        continue
                    was, now = rx[2] == truth, ry[2] == truth
                    tally[f"{'right' if was else 'wrong'} -> {'right' if now else 'wrong'}"] += 1
                    if was and not now:
                        worse.append((cap, truth, rx[2], ry[2]))
            else:
                for ry in y[j1:j2]:
                    tally["added, right" if ry[1] and ry[2] == ry[1] else "added, not placed"] += 1
                tally["baseline rooms with no counterpart"] += i2 - i1
    return tally, worse


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--save", action="store_true", help="save this run as the baseline")
    ap.add_argument("--code", help="a checkout whose mud/ to run instead of this one")
    args = ap.parse_args()

    if not glob.glob(str(CAPTURES / "*.bin")) or not MAP.exists():
        print("regress: no captures or no map.sqlite here -- nothing to replay")
        return 0
    sys.path.insert(0, str(Path(args.code).resolve() if args.code else HERE))
    clock = [0.0]
    time.time = lambda: clock[0]              # the capture's clock, not ours

    rooms = replay_rooms(clock)
    total = sum(len(v) for v in rooms.values())
    if args.save:
        BASELINE.write_text(json.dumps(rooms))
        print(f"regress: baseline saved -- {len(rooms)} captures, {total} rooms -> {BASELINE}")
        return 0

    failures = []
    if BASELINE.exists():
        tally, worse = score(json.loads(BASELINE.read_text()), rooms)
        print(f"regress: {len(rooms)} captures, {total} rooms, against 3K's own titles:")
        for key, n in sorted(tally.items()):
            print(f"  {n:>6}  {key}")
        if worse:
            failures.append(f"{len(worse)} rooms placed right before are wrong now")
            for cap, truth, was, now in worse[:25]:
                print(f"    {cap}: 3K said {truth!r}, was {was!r}, now {now!r}")
    else:
        print("regress: no baseline yet -- run with --save on the last release")

    total_titles, lost = swallowed_titles()
    print(f"regress: {total_titles} marked titles, {lost} swallowed")
    if lost:
        failures.append(f"{lost} room titles never reached the mapper")

    changed = gag_changes_nothing(clock)
    print(f"regress: a gag that matches nothing changed "
          f"{len(changed)} capture(s){': ' + ', '.join(changed) if changed else ''}")
    if changed:
        failures.append("a gag that matches nothing changed what is shown")

    errors = [c for c, v in rooms.items() if any(r[0] == "ERROR" for r in v)]
    if errors:
        failures.append(f"replay raised in {', '.join(errors)}")

    print("regress: " + ("FAILED -- " + "; ".join(failures) if failures else "nothing got worse"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
