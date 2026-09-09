#!/usr/bin/env python3
"""Read 3kdb's bot library into routes the client can walk.

https://github.com/jmitchell33/3kdb is a TinTin++ architecture for 3K with a
few hundred routes in it -- the accumulated knowledge of which rooms hold
which monsters and in what order to visit them, which is not something worth
rediscovering by hand.

The reading itself lives in `mud.tintin`, because the client does it too: the
"update bots" button pulls the same files from GitHub and runs the same
importer.  This is the command-line way in.

    python3 tools/import_bots.py ~/src/3kdb [scripts/routes.json]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mud.botstore import RouteStore  # noqa: E402
from mud.tintin import import_bots  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: import_bots.py <path to a 3kdb checkout> [routes.json]")
        return 2
    root = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else Path("scripts/routes.json")

    class Bare:                            # a store needs no host to load files
        bots = None

    routes = RouteStore(Bare(), out)
    routes.load()
    got = import_bots(routes, root, note=print)
    if got["missing"]:
        print(f"no {got['missing']}", file=sys.stderr)
        return 1
    print(f"\n{got['added']} routes imported, {got['kept']} left alone "
          f"(yours), {got['skipped']} skipped, into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
