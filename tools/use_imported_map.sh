#!/bin/sh
# Swap the imported world map in, keeping what was walked by hand.
#
# The walked map holds only a couple of dozen rooms, but it also holds the
# session log -- what was said, and where -- which is not reproducible.  So it
# is moved aside rather than removed.
#
# Run with the client stopped: renaming a SQLite file a live process has open
# is how a database gets corrupted.
set -e
cd "$(dirname "$0")/.."

# Anchored: an unanchored pattern also matches the shell running this script,
# and any other command line that merely mentions the client.
if pgrep -f "^python3 -m mud" >/dev/null; then
    echo "the client is still running -- stop it first" >&2
    exit 1
fi
if [ ! -f map-imported.sqlite ]; then
    echo "no map-imported.sqlite; run python3 -m mud.tintin first" >&2
    exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
if [ -f map.sqlite ]; then
    for ext in "" -wal -shm; do
        [ -f "map.sqlite$ext" ] && mv "map.sqlite$ext" "map-walked-$stamp.sqlite$ext"
    done
    echo "kept the walked map and its log as map-walked-$stamp.sqlite"
fi
mv map-imported.sqlite map.sqlite
echo "the imported world map is now map.sqlite"
