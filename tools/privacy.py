"""Check that nothing of anybody's is about to be published.

    python3 tools/privacy.py

The repository is public and the captures are not: they hold other people's
conversations, captured while they were simply playing.  Their names have
leaked into the code twice -- test fixtures written from live captures, and a
`hug <name>` in a recorded command -- so this looks for them rather than
trusting anyone to remember.

The list of names is never written down in the repository, which would be the
leak.  It is taken from the captures themselves -- everybody who spoke on a
channel or sent a tell -- plus captures/private-names.txt, one per line, for
names that appear nowhere in a capture.  Words that happen to be names on 3K
(and the placeholders the tests use on purpose) are allowed.

Also checked: no NUL byte in any text file.  One went into a script once, by
way of an escape sequence written as the real thing.
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CAPTURES = HERE / "captures"
EXTRA = CAPTURES / "private-names.txt"

#: Placeholders the tests use on purpose, and ordinary words that 3K lines
#: can put where a speaker goes.  "badger" is a folder in 3kdb's own public
#: repository, which the update tests name.
ALLOWED = {
    "player", "other", "friend", "someone", "buddy", "speaker", "chosen",
    "typed", "you", "mud", "insert", "see", "everybody", "wave", "badger",
}

TEXT = {".py", ".js", ".html", ".css", ".md", ".txt", ".json", ".cmd",
        ".pem", ".toml", ".cfg", ".ini", ".wxs", ".yml", ".yaml", ""}


def names() -> set[str]:
    found: set[str] = set()
    for path in glob.glob(str(CAPTURES / "*.bin")):
        text = Path(path).read_bytes().decode("latin-1")
        found.update(m.group(1).strip() for m in
                     re.finditer(r"#K%\d{5}\d{3}CAA[^~]*~[^~]*~([^~]+)~", text))
        found.update(m.group(1).strip() for m in
                     re.finditer(r"#K%\d{5}\d{3}BAB~?([^~\n]+)~", text))
    if EXTRA.exists():
        found.update(l.strip() for l in EXTRA.read_text().splitlines()
                     if l.strip() and not l.startswith("#"))
    return {n for n in found
            if re.fullmatch(r"[A-Za-z][A-Za-z'-]{2,}", n) and n.lower() not in ALLOWED}


def files() -> list[Path]:
    listed = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True,
                            text=True).stdout.split("\n")
    new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                         cwd=HERE, capture_output=True, text=True).stdout.split("\n")
    return [HERE / f for f in sorted(set(listed) | set(new)) if f and (HERE / f).is_file()]


def main() -> int:
    who = names()
    pattern = (re.compile(r"\b(" + "|".join(sorted(map(re.escape, who))) + r")\b", re.I)
               if who else None)
    leaks, nuls = [], []
    for path in files():
        data = path.read_bytes()
        if path.suffix.lower() in TEXT and b"\x00" in data:
            nuls.append(path.relative_to(HERE))
        if pattern is None or path.suffix.lower() not in TEXT:
            continue
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            hit = pattern.search(line)
            if hit:
                leaks.append(f"{path.relative_to(HERE)}:{number}: {hit.group(0)!r}")
    print(f"privacy: {len(who)} names from the captures and {EXTRA.name}, "
          f"{len(files())} files checked")
    for leak in leaks:
        print(f"  NAME  {leak}")
    for path in nuls:
        print(f"  NUL   {path}")
    ok = not leaks and not nuls
    print("privacy: " + ("clean" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
