# Dank Mud Client

A MUD client for [3Kingdoms](https://3k.org), built around MIP — the protocol
3K already speaks, and which no current client uses properly.

Python owns the socket, the protocol, world state and scripting. The browser is
a renderer, fed typed JSON over a WebSocket. **No third-party dependencies**: a
fresh checkout runs on a bare Python 3.12 on any OS.

```bash
python3 -m mud --web --app    # a window of its own
python3 -m mud --web          # then open http://127.0.0.1:8080
python3 -m mud                # console only
python3 tests/run.py          # the suite
```

Over SSH, forward the port: `ssh -L 8080:localhost:8080 you@host`.

## Why MIP matters

Most MUD clients scrape text. 3K pushes structured data alongside it — hit
points, guild state, room contents, tells, chat, and a combat round counter —
so most of what you would normally write a regex for arrives as fields.

That changes what the client can do. Room objects come with **command templates
from the MUD itself**, so the sidebar can offer a working `kill` button per mob.
The combat round is a counted tick, so an enemy health bar steps once per round
instead of jittering. Guild lines carry label/value pairs with colour as
*status*, so guild state renders without knowing anything about any guild.

## The protocol is not what the documentation says

MIP is described by `PortalMIP9.pdf`, and implemented by Portal (Delphi source
released, unbuildable) and uPortal. All three disagree with the live MUD.

Reconstructed reference, with sources for each claim:
<https://claude.ai/code/artifact/4b17e0cc-e04b-4b29-b142-37c4fdfdcde1>

Corrections that matter if you touch `codes.py`:

| | |
|---|---|
| Composite payload | tags and values **alternate** (`A~312~C~300`), not `A312~C300` as documented |
| `DDD` exits | tilde-delimited on the wire, not space-separated |
| `HAA` / `HAB` | room contents and scenery — **in no specification and no released client** |
| Composite `N` | combat round counter — likewise undocumented |
| `BBA`–`BBD` | gauge *labels*, called "masks". 3K never sends them |
| `^^` | escape for the delimiter, documented nowhere |
| Ranges | hp observed at 31207 against a documented ceiling of 9999 |

**The wire is the specification.** Assume more codes exist. `tools/analyze.py`
on a capture reports anything unrecognised.

## The map

The map is imported, not walked.  `3k_shared.map` -- a TinTin++ map file --
holds 49,494 rooms, 144,768 exits and 777 areas, and loads in three seconds::

    python3 -m mud.tintin ~/3kdbimport/3k_shared.map \
        --into map.sqlite --speedruns ~/3kdbimport/speedruns.tin

Room numbers are kept as room ids, because the speedrun list and years of
scripts refer to them.  An imported map is **locked**: it is corrected, never
grown.  A room it does not contain is far likelier to be one the client failed
to recognise than a room that does not exist, and adding it makes a duplicate
nothing will ever join up.  The exception is a room whose *name* the map has
never heard of, which 3K does gain; those are tagged and `/new` lists them.

What is deliberately not imported is any claim about what a room looks like.
tt++ identifies rooms by matching descriptions; this client identifies them by
where you walked.  Fingerprints are learned by visiting, so the map grows more
certain as it is used rather than starting out sure and being wrong.

`tools/repair_map.py` brings an older import up to date;
`tools/import_bots.py` reads 3kdb's route library.

## Knowing where you are

3K sends no room id.  Position is inferred from movement -- you know where you
are because you know where you were and which way you walked -- and everything
else only ever checks that inference or recovers it.

Having the whole map does not answer this.  It says what the world is shaped
like; it cannot say where in it you are standing.  Once you are anchored,
walking *is* a map lookup -- the map is asked where `n` goes from here and
that is the answer -- but the anchor has to be got in the first place, at
login, and got again every time something moves you without a command: a
teleport, a follow, a death, a linkdeath.

Three things do that.  The room title, if the character has `room_short_pref`
set, arrives with every room and arrives at once, where `BAD` names fewer than
half of them and does it on the tick; it is asked first, because the map has a
name for every room.  Then the fingerprint -- exits and scenery.  And when
several rooms still look alike, the one next door to the room we were last
sure of is the one we are in, which is what tells Tree of Life from Tree of
Life 2.0, and there are fourteen such pairs.

Some of it is irreducible.  3K has sixty-four rooms called `A Dark Square`
with the same four exits, and no map can say which one you are on -- you have
to walk and see which way the exits run out.  Over the captures on disk the
title cut the unplaced arrivals from 62 to 48 and the longest spell of not
knowing from 13 arrivals to 7; the rest is the chess board being a chess
board.

`/bind` anchors it by hand, `/here` says where it thinks you are, `/lost`
tells it that it is wrong.

### The markers do not reach the screen

`Set ANSI prefixes` wraps each kind of line in a marker so the client can read
it, and the client takes them straight back out again on the way to the
terminal, the log and the triggers.  They are scaffolding for the parser, and
a player who types `look` should not have to read around it.  A room title
comes back to the 78 columns it had before the markers existed, with 3K's own
map where it drew it.

Three things make that more than a search and replace, and all three are in
`mud/prefixes.py`:

- A marker can straddle a read, so a tail that might still turn out to be one
  is held back.  A prompt flushes it, so nothing waits on the network.
- `room_long` closes on a line of its own, so a marker that is the whole line
  takes the line with it -- but only when a marker is why the line is empty.
  3K sends plenty of blank lines of its own.
- `Variable room_short_pref set to: -R-_` is the one line where the marker is
  the message.  Blanking it there would read as the setting having failed, at
  the exact moment somebody is watching to see whether it worked, so a line
  that names one of the variables keeps its markers.

## The handshake

MIP does not start until the client announces itself with `3klient <sec>~<ver>`,
and there is exactly one moment to do that: after the login and not one byte
before.  Announced at the name prompt, `3klient 40142~1.0` is simply typed in
as somebody's character name.

This used to watch for a phrase in the login spam, the way Portal does, and the
phrase was `Welcome`.  Over the forty logins in `captures/`, that matched
*after* the login five times, matched *before* it seven times, and did not
match at all in the other twenty-eight -- 3K answers a reconnect with
"3Kingdoms welcomes you back from linkdeath", which does not contain it.  So on
the ordinary path the handshake never fired and had to be sent by hand.

It now waits for the login itself: the password question having been answered,
whoever answered it.  That is read from the text rather than from the client's
own state, so it holds just as well for somebody who typed their name in at the
terminal.  Forty logins, fired every time, never early.  `--no-jumpstart` turns
it off; `/js` still forces it.

## Link death

3k.org drops you for a reboot, for a bad hop, and for nothing at all.  The map,
the rules, the log, the routes and the browser on the other end of the
websocket are all still perfectly good when it happens -- they belong to the
character, not to the socket -- so the read loop is the inner one and the
client outlives the connection.  It goes back after two seconds, then four,
eight, sixteen, capped at a minute, and it does not give up: a reboot takes as
long as it takes, and a client that stops after five tries is one you find dead
an hour later.  The sidebar counts down while it waits, because a client
retrying in silence looks exactly like one that has given up.

Coming back, it types the name and password again.  Those come from the
character rather than from the login, which clears the password the moment it
has been sent, and then the handshake goes out again -- MIP is something the
MUD does for a connection, and the new one has never heard of us.

What does not survive the gap is everything the socket owned: half a MIP
message, half a line, half a room description, a route walking somewhere, and
the belief that we know which room we are standing in.  The first three would
glue onto the new connection and desync the parser.  The fourth is worse than
useless -- a route carries on counting steps while there is nothing to send
them down, and arrives convinced it is somewhere it has never been.  The map
goes honestly unsure and works out where you are from the first room block,
which is the same thing it does after a death.

`--no-reconnect` quits instead, which is what a replay wants: the end of the
input is the end.

A hang-up we asked for is a different thing, and the difference is the whole
point of the **Disconnect** button: it stops the bots, puts the log and the map
on disk, marks the session finished, closes the socket, and then leaves it
closed.  It does not send `quit`.  Closing the connection and logging the
character out are different acts with different consequences, and a button
labelled Disconnect should only do the one it says -- so you are link-dead
rather than logged out, exactly as if the line had dropped.

Everything else was already saved: rules and routes are written the moment you
edit them, and the log is flushed on a timer.  What the session row could not
know until now is when it ended -- a row with no end never finished, because
the client was killed or link-died and nobody brought it back -- and who was
playing, which is not known when the row is made: the client is up and logging
before anybody has picked a character.  Both are recorded now, so a session in
the log is a complete record of itself.  A session that comes
back two seconds after you press Disconnect is a session with a broken button.
What closes is the connection and not the window: the client, the map, the log
and everything in Options stay up.  The way back is the character screen, which
brings itself up when you disconnect -- after a hang-up "who is playing" and
"how do I get back on" are the same question, and one screen answers both.
Picking a name connects, answers both prompts and sends the handshake, in that
order and without serving a backoff nobody caused.

Whoever was picked last is remembered in memory for the life of the client, so
a link death does not leave you sitting at the password prompt because you
chose not to save the password.  It is written nowhere.

## Characters

A player has several characters and they are not the same person.  One
character's aliases are muscle memory for that character's guild; on another,
half of them are commands that do not exist.  So triggers, aliases, events, stat
watches and the line markers follow the character::

    profiles/characters.json      the list, and any password you asked us to keep
    profiles/player/rules.json   triggers, aliases, events, watches
    profiles/player/prefixes.json

The map and the routes deliberately do not.  A road is in the same place
whoever walks it, and splitting fifty thousand rooms per character would mean
walking them again for nothing; routes are paths across that map, so they go
with it.

The login screen shows itself while nobody has said who is playing, and gets
out of the way once somebody has -- by picking a name, by skipping, or by
typing their own name past it.  `--character NAME` skips it altogether.
Settings from before profiles existed seed the first character that asks for
them, copied rather than moved, so the second one starts from the same place.

If you ask the client to keep a password it goes in `profiles/characters.json`
in plain text, in a file created private to you.  That is as much as a client
can promise and the screen says so.  It never reaches the browser (which is
told only whether one exists), the capture, or the log -- the one string that
funnels through `Session.send` and is not written down.

## Panels

Nothing floats.  Panels that can be dragged anywhere are panels you have to
place, and they sit over the text while you decide.  The sidebar reads top to
bottom in the order you look at things: three buttons, then the map, then the
session -- the connection, the pacing, and what a route is doing -- then combat
when there is any.

The buttons come first because they are the ones you reach for without looking:
**Options**, **Bots** (the routes tab in one press) and **Disconnect**.
Disconnect is last and set apart, being the only press in the sidebar you
cannot take back by pressing it again -- a mis-click leaves you link-dead in
whatever room you were standing in, so it asks first.

Tells, emotes and channel traffic share one window across the top of the
output.  MIP separates the first two from the third -- `BAB` is personal, `CAA`
is channels -- and this was two panels for a while on that basis, but the split
is the MUD's idea of the difference rather than the reader's.  Every channel
gets a tag under the title bar, `tell` among them, and switching one off hides
it; the count says how many are showing out of how many there are.  Clicking a
line puts the reply in the input box.

The map is docked there rather than floating over the terminal.  It is the
panel you glance at most, and one you have to place somewhere is one that is
in the way of the text underneath it.  Click its header to roll it up.

It does not move and does not scale: where you are is the middle, always, at
one size.  A map you can drag off centre or zoom out of is one that needs
putting back before it can be read, and the whole point of it is being
readable at a glance without being touched.  Clicking a room still walks
there, and double-clicking one renames it.

The room panel is off unless it is asked for, under Options -> Panels, and
sits at the bottom when it is on.  It lists everything in the room with a
button for every action the MUD says each thing takes, which is worth having
and is not worth a third of the sidebar when you are not using it.

A running route shows which step of how many, because "walking" on its own
does not tell you whether to wait for it or go and do something else.  A
repeating route's bar shows the current lap rather than filling up and staying
full.

The terminal takes the width it is given.  It can be capped in columns under
Options -> Panels, but that is off by default: capping it sounds right and
looks wrong however generously it is set, because the text ends up in a block
with a margin beside it, and a margin is not a tidy edge.  The sidebar is
where the width goes instead, because it has something to do with it -- the
map takes its height from its width, so every extra thirty pixels is another
column of rooms in both directions.  When the cap is on it goes on the output
area rather than on the terminal, so the messages window narrows by the same
amount and the two stay lined up.

Everything shares one gutter, `--gut`, so the terminal's first line, the
vitals strip, the input box and the top of the map all start on the same
lines rather than within a couple of pixels of each other.

Which panels are shown is kept in the browser rather than on the character:
it is about the screen in front of you, and a second window on a second
monitor can reasonably want a different one.

## Layout

```
mud/scanner.py    MIP framer: character-wise, survives any packet split
mud/codes.py      typed decoders, guild-line markup
mud/state.py      world state, rebuilt from MIP
mud/events.py     one bus; everything downstream subscribes here
mud/clock.py      the 2s server beat, from tag N or tag E
mud/outbound.py   APM governor (see below)
mud/login.py      the two questions 3K asks before it lets you in
mud/profile.py    characters, and which settings follow one
mud/prefixes.py   the line markers, and taking them back out
mud/scripts.py    user scripts, hot-reloaded
mud/rules.py      GUI-managed rules, same engine as scripts
mud/web.py        stdlib HTTP + WebSocket server
mud/ui/           browser: terminal, panels, rule editor
tools/analyze.py  turn a capture into a protocol inventory
tools/wscheck.py  prove the server without a browser
```

### The map is corrected, never grown

That covers its edges as well as its rooms.  When the command is not a way out
of the room we were in, we are guessing at which of several commands in flight
caused the block, and a guess does not go into an imported map as fact.

Nothing is lost by declining.  DDD lists every way out, and the 144,768 edges
that came with the map already carry the ones that are not directions.  What
gets refused is the likes of `embrace void` and `board cot` -- abilities that
work from anywhere, which as an edge from the one room you happened to use
them in is a shortcut the router would believe in.

`tools/prune_edges.py` takes out ones written before that rule existed.  It
prints and stops; `--command` narrows it and `--yes` does it.  It spares
anything that came with the map, anything the room lists as an exit, and any
plain direction -- tt++ truncates a long room title at sixty characters, so a
missing `e` is a gap in the record rather than an invented exit.

### Which command caused this room

Oldest first, because that is the order the MUD ran them in.  Except that a
route sends its housekeeping and its next step in one breath -- `wrap all`,
`disperse corpse`, `divvy gold`, `w` -- and only the last of them moves.
Oldest-first hands the block to `wrap all`, the room has no such way out, the
map cannot place it, and the client is lost with a perfectly good `w` three
places down the queue.  On the chessboard route that happened at every kill.

So the queue skips past commands the room you are standing in has no way out
for -- DDD lists them all, and the map knows the ones that are not directions.
Skipped only, never reordered: if the oldest is a way out then it is the
answer, because two moves in flight arrive in the order they were sent.  And
if none of them is a way out, the oldest is still the best guess.

Over the captures on disk that halved it: 716 arrivals, position dropped 35
times before and 19 after, and the chessboard run went from losing itself at
the first kill to walking the whole board.

## Three things that are easy to get wrong

**Watches must be edge-triggered.** 3K sends *two* composites per combat round,
so "hp below 35" fires twice a round, forever, if it triggers on level rather
than on the crossing. That is how you quaff forty potions.

**Pace by APM, not by the round.** 3K counts non-directional commands per
minute and takes an interest above 100 — that is 1.67/second, where one command
per 2s round is 30/min. Pacing to the round is three times stricter than the
rule and adds two seconds of latency to a single trigger. Send immediately;
throttle near the ceiling. Movement is exempt, and `DDD` tells you what counts
as movement in the room you are standing in.

**Never parse MIP by line.** Messages arrive back-to-back with no separator,
split across TCP segments at any byte, and payloads contain newlines. The
character count is the only delimiter. `scanner.py` is a character-wise state
machine for this reason, and its tests replay a real capture split at every
possible byte.

## Finding things

One search box, beside the panel title, filtering whichever list is showing --
routes, triggers, aliases, events, watches, script rules.  `/` jumps to it and
Escape clears it before it closes anything.

It matches every word anywhere, in any order, and it looks at what a rule
*does* as well as what sets it off: half of what you remember about a rule is
its action -- "the one that quaffs" is a search for the command, and the
pattern that fires it is the part you have forgotten.  A route's path is
searched for the same reason, because with sixty-seven imported from tt++ the
thing you remember is often a step rather than a name.

The counts on the tabs stay the totals.  A search is a way of looking at what
you have, not a change to it.

## Routes

A route is a name, a path and what to attack along it -- the tt++ botpath,
as a form rather than a file.  Paths read the way people write them:
`n n e s w`, `3n 2e s`, semicolons for a pasted tt++ path, and braces for a
step that is several commands (`{pick fruit;get seed;d}`).

Every walk goes one step at a time, waiting for the room block the last one
produced.  Sending them together looks like a speedwalk and is not: after the
first step you are somewhere else, and the rest go out from a room they were
never meant for.  A step that produces nothing is *looked* at rather than
assumed to have failed -- some moves send no room block at all -- and a way out
that really does not work is remembered, so routing stops choosing it.

## Timers

    /tick 290 xp          send it every 290 seconds, and keep doing it
    /ticks                the ones that are running
    /untick xp            stop that one; /untick all stops the lot
    /delay 5 quaff heal   send it once, in five seconds

A tick is a rule like any other -- a fifth kind beside triggers, aliases,
events and stat watches.  So it is stored with the character, editable in the
panel, renders as a script like the rest, and goes through the same governor:
a timer is not a reason to trip 3k.org's APM ceiling.  `/tick` is a way of
writing one rather than a second mechanism doing the same job, and it names the
timer after what it sends, so `/untick xp` works without anybody naming
anything and setting the same tick twice replaces it instead of stacking a
copy nobody can see.

They run on the game's own two-second beat rather than the wall clock, which
means two things.  Anything under two seconds is a number the client cannot
keep, so it is refused.  And nothing fires until MIP is flowing: the beat
free-runs when there is no signal to lock onto, and that includes sitting at
the login prompt, where sending `xp` every 290 seconds types it into the
password box.

A delay is not stored.  It happens and it is gone.

## Updates

On a client that has never had a map -- a fresh install -- the world is fetched
once, at startup, in the background.  Somebody who has just double-clicked an
installer should not have to be told that the first thing to do is go and find
fifty thousand rooms.  It takes about ten seconds and the client is usable
while it runs; the login screen is what they should be looking at anyway.
Measured on an empty directory: 49,494 rooms, 142,239 exits, 777 areas, 399
named destinations and 67 routes.  `--no-bootstrap` skips it, and a failure is
a note rather than a stop -- the client works without a map, and Options ->
Updates will retry.

The map and the route library came from
[jmitchell33/3kdb](https://github.com/jmitchell33/3kdb), a TinTin++ setup for
3K, and it keeps growing.  **Options -> Updates** asks what has changed and
takes it.

Three paths are watched: `common/map/3k_shared.map`, `common/map/speedruns.tin`
and `common/bot` -- the last as a directory, so one sha covers all hundred and
seventy route files.  One API call gets every sha; the tarball is one
compressed request rather than a hundred and seventy.  Against a map that was
already current the whole thing takes four seconds.

All three are data.  The map is parsed into SQLite and the bot files are read
with a regex; nothing pulled here is executed, and that is the reason this is a
button at all.  `scripts/` is deliberately not on the list -- those are Python
and they hot-reload, so pulling them would be running somebody else's code as
you.

Nothing is replaced.  The map is merged, which only ever adds; a route you have
named is left alone.  Both were measured before they were trusted, against a
map that had been played on: a plain re-import duplicated every region, reset
every visit count, wiped every fingerprint learned by walking and put a room
renamed by hand back to the name tt++ gave it.

Exits carrying TinTin++ directives are filtered on the way in -- `#map goto
$puddle_room` moves tt++'s own cursor and typed at 3K means nothing while still
counting against the rate the MUD watches.  Filtered, not reformatted: tt++
writes `search;open trapdoor; stairs` with a space after the semicolon, and
rebuilding that string without the space makes a second exit beside the first.
`/repair` folds any that are already there, keeping whichever has been walked.

The tarball is untrusted input, so only plain files under a path we asked for
are taken out of it -- a name with `..` in it, an absolute path, or a symlink
pointing at your keys is dropped before anything is written.

## Scripting

Rules can be built in the UI (Triggers & Aliases panel) or written as Python in
`scripts/`, which hot-reloads on save. Both register into the same engine, and
any GUI rule renders as the equivalent script via **as Python** — the panel is
a door into scripting, not a walled garden.

```python
@on("tell")
def _(t): send(f"tell {t.who} omw")

@when(lambda p: p.hp_pct and p.hp_pct < 35)     # edge-triggered
def _(): send("flee", PANIC)

@trigger(r"(?P<who>\w+) has arrived")
def _(m): log(m["who"])

@alias("gk", mode="command")
def _(m): send(f"kill {m['args']}")
```

`scripts/_example.py` shows every hook. Files starting with `_` are not loaded.

## Scrollback

A refresh used to empty the terminal, and a refresh is what you do after every
change to the client -- so the answer to "what just happened" went away exactly
when you wanted it.  A terminal that has just opened is now given the last four
hundred lines of the session it is joining.

It comes from the log rather than from anything held in memory, which means it
survives the client being restarted too, and which means it comes back without
colour: lines are stored ANSI-stripped, because nobody searches for an escape
sequence and the colours would swamp the index.  So it is drawn dimmed and
ruled off -- what happened, as against what is happening.

The buffer is read as well as the table.  The log flushes on a timer, so the
newest few seconds are still in memory, and those are exactly the part you were
looking at when you refreshed.

Tells and channels are not replayed here.  They have their own window and are
seeded into it separately; putting them in both would be a second copy of every
line.

## Captures

Every session records to `captures/` — raw bytes plus a timing sidecar, so a
session can be replayed through the scanner exactly as it arrived.

```bash
python3 tools/analyze.py captures/20260908-211238
```

Reports every code seen with provenance, composite tags, discovered guild-line
fields, room object types, and the composite inter-arrival histogram that showed
the 2-second beat. Captures are gitignored: large, personal, irreplaceable.

## Installing it on Windows

A 3K player has no Python and should not have to get one, so the client ships
with an interpreter.  The embeddable distribution from python.org is a zip of
exactly that -- no installer, no registry, no PATH -- which makes the whole
client a folder you copy, and a folder is what an installer wants to lay down
anyway.

```bash
python3 tools/build_windows.py --zip
```

Twenty-two megabytes, ten zipped.  It runs anywhere, Linux included: nothing is
compiled and nothing is executed, only unpacked and copied.  What it cannot do
is test it, which needs Windows.

    3k\
      python\         the interpreter, pinned to a version and a hash
      mud\            the client
      3k.cmd          start it
      3k-console.cmd  ...keeping the console, for when it does not start

It opens in a window of its own rather than a tab.  The interface has to be a
web page -- that is the only way to draw a terminal, a map and a dozen panels
without a toolkit -- but a tab among thirty other tabs is not an application.
Chromium's app mode gives the page a window with no address bar, no tabs and
its own entry in the taskbar, and Edge ships with Windows 10 and 11, so there
is always one.

The window gets a profile directory of its own.  Without one it joins the
browser the player already has open: their extensions run against it, their
session is shared with it, and closing it closes nothing, because the process
was already running.  With one it is a separate program that can be waited on
-- and closing the window is how you quit an application, so that is what it
does: the log and the map go to disk, the bots stop, the session row is marked
finished, the socket closes.  It is Disconnect, pressed a different way, and
like Disconnect it does not send `quit`.

Everything the client keeps -- the map, the characters, the triggers, the logs
-- goes to `%LOCALAPPDATA%\3k` rather than beside the program, because an
installer puts the program in Program Files where the user it installed for
cannot write.  That also means the folder can be replaced wholesale by an
update without touching any of it.

Installed, it started and then closed again with no error at all.  `pythonw.exe`
has no standard streams -- `sys.stderr` is `None` -- so the first thing that
printed raised `AttributeError` inside a process with nowhere to report it.
There is a log now: with no console, the streams are pointed at
`%LOCALAPPDATA%\dankclient\client.log`, and an unhandled exception is written
there before the process goes.  A client that fails invisibly cannot be
reported, and "it closed" is not something anybody can act on.

Three more things were wrong the first time it ran on Windows, and all three are the
same kind of thing -- a client somebody double-clicked cannot answer a problem
with a traceback.

Something already had port 8080, and the client died on it.  `--web` given
without a number now means "8080, or the next free one", and says which it
used; a port actually typed is still honoured exactly and still fails loudly,
because nobody types a port number and means "or whatever".

Every line the client printed about itself arrived with a literal `<-[2m` in
front of it: Windows consoles do not interpret escape codes unless asked, and
the asking is a Win32 call.  It asks now, and drops colour entirely when the
console will not have it or when the output is being redirected to a file.

And a path was printed with a trailing forward slash on a machine that uses
backslashes.

## The installer

```bash
sudo apt install wixl          # msitools; builds MSIs on Linux
python3 tools/build_msi.py
```

Eleven megabytes, carrying the twenty-two megabyte folder.  Built on Linux, so
there is no Windows build host to keep.

It installs **per user**, into `%LOCALAPPDATA%\Programs\Dank Mud Client`.
Program Files would need an administrator, and asking somebody to elevate to
install a MUD client is a lot for a program that only ever writes inside their
own profile -- so there is no UAC prompt at all.

Three pieces of bookkeeping make an upgrade an upgrade rather than a second
copy.  The upgrade code is pinned and must never change: Windows matches
versions by it, and a changed one installs 0.2.0 beside 0.1.0 with neither
aware of the other.  Component GUIDs are derived from the file path rather than
generated, so two builds of the same file agree and an upgrade replaces it
instead of leaving both.  And `RemoveExistingProducts` runs after
`InstallInitialize`, so the old files go before the new ones arrive.

Your map and characters survive all of that, because they were never in the
program folder: `%LOCALAPPDATA%\dankclient` is a different place, and the
installer has no reason to touch it.

It has a licence dialog, a progress bar and a finish dialog that says where it
went -- `wixl` ships the WixUI_Minimal set, off unless `--ext ui` asks for it.
The first installed build had no interface at all, which meant it landed
somewhere without saying where and left a Start Menu entry and no account of
what it had done.

The client says the same things whenever asked, in **Options -> About**: the
map, the characters, the scripts, the captures and the log, each with a word
about what it is.  "Where is my map" is a question that gets asked more than
once -- before an update, before a backup, when something has gone wrong.

The built MSI was taken apart again to check: 84 files in, 84 out, every
SHA-256 matching, installing to the right directory with the "elevated
privileges are not required" bit set.

The interpreter is pinned by version *and* by SHA-256: a build that quietly
picks up a different one is a build whose bugs cannot be reproduced.  What the
client needs from it was checked rather than assumed -- `_sqlite3` for the map,
`_ssl` for the update check, `_socket` for the MUD, and `pythonw.exe` for a
launch with nothing behind it.

## Client commands

Typed in the browser or the console; they never reach the MUD.

    /help  /state  /clock  /find <text>            what happened, and where
    /here  /bind <where>  /lost  /go <name>        where you are, and getting
    /marks [text]  /region <name>  /regions        about
    /name  /merge <id>  /forget <id>  /new         correcting the map
    /dupes  /repair  /lock  /unlock
    /bots  /stop  /prefixes [set]                  what is driving the
    /scripts  /reload  /test <line>  /triggers     character, and scripting
