# The map and getting about

The map is 3kdb's, tens of thousands of rooms, and it follows you as you walk.

- **Click a room** on the map to walk there.
- `/go <name>` walks to the nearest room with that name or mark: `/go bank`. The whole way goes at once.
- [Options → Marks](options:marks) lists every place `/go` knows, nearest first, with a **Go** button. `/speedruns` shows the same in the output.
- `/here` says where the map thinks you are. If it does not know, `/go` looks first and walks if the look finds you.
- A long walk goes out in chunks, and each is checked against where the map says it should have got to. A chunk that lands somewhere else stops the walk rather than running the rest of the path blind.
- `/lost` tells it that it has you in the wrong place; `/bind <where>` says where you really are.
- `/name <text>` renames the room you are in.

The map finds you by the markers set in **Getting started**, and by where you walked. If it loses you, walk a room or two.

## The map does not grow

The map is 3kdb's, and it stays 3kdb's. Rooms are never added by walking: if the client does not recognise where you are, it says it is lost rather than invent a room, because an invented room is a duplicate of one already on the map and nothing ever joins the two up again. New rooms arrive from 3kdb, through [Options → Updates](options:updates).

- `/unlock` lets the map add rooms, for mapping somewhere the import does not cover. `/lock` puts it back.
- If the map itself looks wrong rather than out of date, [Options → Updates → Fresh copy](options:updates) drops your copy and takes 3kdb's again. Your session log is kept.
- `/here` and `/lost` and `/bind` are how you get found again; see above.

## Is somebody else's map the same as yours?

Nobody can hand you their map: it is tens of megabytes, and the file holds their session log as well. A summary can be sent instead.

- `/mapsum` prints your map's digest and what it was built from, and writes `map-summary.json` in your data folder. Send them that file.
- `/mapcheck <file>` compares the summary they sent with your own. The same digest means the same map.
- When they differ it says how: a different 3kdb map file, the same file built by a different importer (**Options → Updates → Take updates** rebuilds it), or areas where one of you has rooms or exits the other does not, widest first.

The summary is counts, digests and area names. Nothing you have walked, said or logged is in it.
