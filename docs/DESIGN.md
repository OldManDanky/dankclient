# Dank Mud Client -- design notes

Why it is built the way it is.  To install and play it, see the
[README](../README.md).

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

### Nobody else's house

3kdb's map was walked by one player, and every `home` in it goes to his
house.  Seventeen public rooms led there -- by `home`, by `home 726`, and by
`.goHome`, his own tt++ alias -- and the house's portal room has shortcuts to
the shop, the bank, the guild and the realms.  So going home looked like the
fastest way anywhere: 57 of 259 routes between rooms around Pinnacle went in
through his door, and every one of them fails for anybody else, whose `home`
goes to their own house or nowhere.  It also placed anyone who typed `home` in
his house, and then wrote their next steps into the map from there.

His tt++ aliases are the same kind of thing.  They start with a dot, they are
commands in his client rather than in 3K, and `.fly;u` and `.land;n` were the
only way the map had into Mystic Seal.  Flying takes something not every
character has, so they are treated exactly like houses.

A way out that only works for whoever walked it is never an edge now.  The
importer leaves them out, a map that already has them is cleaned once when it
is opened, walking never records one, and the router ignores any that come
back.  Measured on a real map: 44 edges went, and none of 259 sampled routes
around Pinnacle was lost or goes through a house any more.  The 1,558 rooms
only reachable that way -- Mystic Seal and the Ruins of the Mad Titan Lord
behind a flight, his house, eight other houses and one clan's hall -- are
still in the map, unreachable: a room is not wrong, only the claim that
anybody can walk into it.  A route that starts in one of them still runs for
somebody who has got there themselves.

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

### Brief mode

3K's `brief on` shows each room's one-line title instead of its paragraph,
and a friend testing it found the map standing still -- "walked from chaos ent
to resid, map still thinks im at chaos ent ... caught back up when i looked".
A capture of the same walk showed why.  In brief mode 3K sends the title,
markers and all, and the room's contents, but **no DDD with the step**.  The
exits arrive only later, behind BAD's two-second sample -- and a DDD after a
BAD is deliberately not a new room, because in long mode that pair is a
repeat.  So no room block ever opened.  `look` sends a full room with its own
DDD, which is why looking caught it up.

So a marked title that has had no DDD of its own a quarter of a second later
makes the room itself: its exits from the title's brackets, the contents that
arrived after it, and the title's own time so the move is credited to the
command that caused it.  The wait comes from 1,127 titles in long mode, where
the DDD follows in a median of 0.03s and 90% within 0.07s; every one that took
longer had no DDD of its own at all.  A second title arriving before the wait
is up settles the first at once, and a title 3K cut off at sixty characters
never makes a room -- half an exit list is how a phantom room was once
invented.  In long mode the DDD always comes first and none of this happens.

Replayed over the brief capture, the released client saw none of the six
rooms and this sees all six, each where 3K's title says.  Over all sixty
captures, measured against 3K's own title for every room with one yardstick
for both versions: 1,160 placed right before and after, 27 wrong before and
right now, 13 new rooms placed right, and none right before and wrong now.

### Finding yourself by name without taking the step twice

Getting every title to the mapper exposed an older mistake in how it finds
itself again when lost.  With the title naming several rooms -- 3K's Chaos
has three called Eastwick with the same four exits -- it narrowed them by the
command just walked, but walked it *from* the named rooms.  Those are where
you might have arrived, not where you started, so the step was taken twice:
a player who walked west into Eastwick was put on Eastwick Road, west of one
of the others, and a room ahead from then on.

Now the named rooms are narrowed by where you might have *been* when that is
known, and whatever narrowing follows may not land you in a room whose name
contradicts the title 3K just printed.  The first fix went further and simply
stayed lost among the named rooms, and the replay showed 79 rooms it had been
getting right turned to lost -- the temples of the Tree of Life are runs of
rooms that share a name, and the old narrowing lands on one of them, which is
right.  Only the contradiction was the bug.

### A description that closes mid-line

Finding that turned up an older bug.  A description ends with its marker, and
only a marker on a line of its own was recognised -- but 3K as often puts it
at the end of the last line of prose, and 249 of the captured descriptions end
that way.  The reader then took the description to go on for ever and read
every room title after it as more description: **289 of 1,134 marked titles,
a quarter of them, never reached the mapper.**  Brief mode, which sends no
descriptions to close one properly, never got its titles back at all.  A
marker at the end of a line closes one now, and so does the next title.

The title reader also recognises a room title with no markers at all, by its
shape -- a name, then its exits in brackets -- but believes it only when those
exits are exactly the ones MIP sends, which a tell with brackets in it will not
manage.  Over every capture that named 175 more rooms and changed none.

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

Right-clicking one colours it -- or rather colours every line like it.  The
colour sticks to the channel or to the person, because a single coloured line
scrolls away and what somebody means is "clan in green" or "this friend in
gold".  A person's colour wins over their channel's, being the more particular
choice, and a channel's shows under its tag so the key is on screen.  Eight
colours, each light enough to read on the dark ground.

**Dings** are chosen in the same right-click menu as the colours, and for the
same reason stick to a channel or a person.  A tell chimes twice and a channel
once, so the two are told apart without looking; the sounds are made with the
browser's own audio, so there are no files to ship.  Never for your own lines,
never for a channel you have hidden, and never more than one every 1.2 seconds
-- a busy channel should be a ding, not a buzzer.  Off until chosen, because an
update should not start making noise on its own.

3K's own bell is the exception.  `wake` puts a BEL in your output, which a
terminal has always rung; xterm only announces it and leaves the sound to the
page, and nothing was listening, so the bell reached the screen and made no
sound.  It rings now, with three notes of its own, and is on unless switched
off -- a bell is somebody deliberately waking you, not chatter.  The scrollback
put back after a refresh has its control characters removed, so an old bell
never rings again.  Browsers refuse to play
anything before somebody has clicked or typed on the page, so the audio wakes
on the first keypress, which in a MUD client is logging in.

The **mine** tag hides your own lines: "I want to see what everybody else
says, not what I sent."  A tell says itself which way it went; a channel line
is yours when 3K names your character as its speaker.  So the client has to
know who is playing even for somebody who typed their name at 3K's own prompt
-- it takes the line typed while the name question is the last thing asked,
and never the one typed at the password question that follows.

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

**The numpad** walks, when asked to: 8 north, 2 south, 5 `look;search`,
`+` and `-` up and down, every key settable to any command or several joined
with `;`.  Off by default, because a new player pressing 8 expects an 8.  The
usual setting is "when the command box is empty" -- a box whose whole text is
selected counts, since that is what keeping the last command leaves -- so it
walks without thinking and is still a number pad mid-sentence.  It is keyed on
the physical key, which the browser reports as `Numpad8` whether NumLock is on
or not, so the digit row is never involved.  Holding a key sends once: auto-
repeat would send thirty `n`s a second into a map you do not know.

**Fonts** has its own tab: the terminal's font, size and line spacing, which
the command box follows, and the messages window's size.  A page cannot ask
the computer for its fonts without a permission prompt, but it can ask about
one font at a time -- text drawn in it comes out a different width from the
fallbacks -- so the list is the fixed-width fonts people actually have,
trimmed to the installed ones, with Other for any name.  Fixed-width because
the terminal is a grid: 3K's maps and tables line up only when every letter
is the same width, and Other says so when a font is not.  A preview draws a
little of a map in the chosen font.  The size of everything else is the
browser's own zoom, Ctrl + and Ctrl -, rather than a second zoom of ours.

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

## The deadman

A bot left walking with nobody at the keyboard keeps walking into whatever
changed while nobody was looking.  So after fifteen minutes -- settable in
Routes & bots, 0 for off -- without a command typed by a person, everything
automated stops: bots and routes pause where they are, and triggers, timers
and script sends are dropped.  The first command typed brings it all back and
the bots carry on from the step they were on.

What counts as a person is what only a person does: a line typed in the box
(numpad included), a click on the map to walk there, starting a route.  What
is held back is dropped rather than saved up, and anything already waiting in
the queue goes when it trips, because somebody coming back should not be met
by a burst of stale commands.  Bots wait *before* each thing they send rather
than having it dropped: a step dropped mid-route reads as a step that went
nowhere, and the route would stop instead of pausing.  Logging back in after
a link death and the MIP handshake are not held -- they keep the connection,
they do not play the character.  It is enforced by the client rather than the
page, so the setting is kept with the map, and checked on the game's beat.

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

## Gags

    /gag <text>           hide every line containing it
    /gags                 the ones in force
    /ungag <text>         show it again; /ungag all

tt++'s `#gag`, and a gag is a trigger with its gag box ticked and nothing
else to do -- so it is stored with the character, listed in the triggers
panel, and a trigger that does something can also gag the line it fired on.
Scripts have `gag(pattern, mode="contains")`.  Only the screen loses the line:
the triggers and the log still see it, as in tt++, and a refresh does not put
it back.

The screen is fed in network chunks rather than lines, and a gag needs the
whole line to decide, so while there are gags a line is held until its newline
arrives.  3K marks nothing as a prompt -- there is not one telnet GA or EOR in
59 captures -- and a prompt has no newline, so an unfinished line is shown
after a tenth of a second rather than waiting for an ending that is not
coming.  If the rest of a line already drawn arrives later and is gagged, the
row is wiped.  With no gags nothing is held at all.

## Updates

On a client that has never had a map -- a fresh install -- the world is fetched
once, at startup, in the background.  Somebody who has just double-clicked an
installer should not have to be told that the first thing to do is go and find
fifty thousand rooms.  It takes about ten seconds and the client is usable
while it runs; the login screen is what they should be looking at anyway.
Measured on an empty directory: 49,494 rooms, 142,239 exits, 777 areas, 399
named destinations and 3kdb's whole route library.  `--no-bootstrap` skips it, and a failure is
a note rather than a stop -- the client works without a map, and Options ->
Updates will retry.

**Options -> About** also says whether there is a newer client than this one.
Asked once, in the background, when the interface first connects: nobody wants
their MUD client stopping to talk to GitHub, and the answer does not change
while they play.  Being offline is an empty answer rather than a message.

It tells you and stops there.  Fetching and running an installer on somebody's
behalf is a different thing entirely, and not one a MUD client should do while
they are in a fight -- so it shows the version, links to the release, and
leaves the decision alone.  A tag nobody can parse counts as older than
everything, which is the safe direction: a release named "latest" should not
make every client in the world announce a new version.

The map and the route library came from
[jmitchell33/3kdb](https://github.com/jmitchell33/3kdb), a TinTin++ setup for
3K, and it keeps growing.  **Options -> Updates** asks what has changed and
takes it.

Three paths are watched: `common/map/3k_shared.map`, `common/map/speedruns.tin`
and `common/bot` -- the last as a directory, so one sha covers all hundred and
seventy route files.  One API call gets every sha; the tarball is one
compressed request rather than a hundred and seventy.  Against a map that was
already current the whole thing takes four seconds.

What is remembered is what was taken **and how it was read**.  The route
library sat at 67 of 3kdb's 145 for a while because `.add_bot` lines with six
fields were skipped and only the seven-field ones matched -- silently, because
a line that does not match is not a line that failed.  3kdb had not changed, so
without this a client that had already pulled would never have taken the fix:
the record saying "we have this" is exactly what would have frozen the bug in.
Each importer carries a version, and bumping it offers the data again.

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

## Reacting to the connection

A rule or a script can hook the connection itself, not just the game:

```python
@on("disconnected")
def _(_): log("the line went")

@on("connected")
def _(_): send("look")            # held until there is a socket, then sent
```

`connected`, `disconnected` and `retrying` are events like any other, so the
Events tab offers them too.  A route that was walking when the line dropped
otherwise just stops, with no way to say so or to start again -- and coming
back is the moment to re-arm whatever was running.

Anything sent while there is no socket waits for one rather than failing.  The
queue used to hand it straight to `send`, which raises with nothing to write
to, so a rule that fired on a disconnect looked broken rather than pending.
The drain checks too: the game's beat keeps coming while the connection is
down, and a drain that only watched the clock would empty the whole queue into
a socket that is not there.

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

## Who can reach it

The interface is served to loopback and nowhere else, and there is no flag to
change that.  Opening the app is how you play on a machine; a second machine is
a second app, not a second window onto this one.  To reach it from elsewhere,
forward the port over ssh -- the startup line prints the command -- which is
real encryption and real authentication instead of a password field over plain
HTTP.

That is not the whole of it, though, because binding to loopback is not the
protection it looks like.  WebSockets are not subject to the same-origin
policy: any page a player visits while playing can open one to `127.0.0.1` and
drive this client -- send commands as them, write triggers that fire later,
read the session log.  The connection comes from their own browser, and both
the port and the message format are public.

So the handshake is refused unless it comes from our own page.  Browsers always
send `Origin`; anything without one is not a browser -- a test, a script, a
tool on the same machine -- and something already running locally can do as it
likes anyway.  The port is deliberately not part of the check, because an ssh
tunnel forwards to whatever local port it likes and the page is then served
from that one.

What the socket accepts is worth knowing, because it is the reason any of this
matters: commands as the character, playing a saved character with a saved
password, writing triggers and routes, and the whole log through `/find`.

## The edges

A pass over everything that touches a network or a disk, in 0.2.3.  Each of
these was reproduced against the client before it was changed, and each fix is
pinned by a test in `tests/test_hardening.py` that failed first.

**A link that dies without a word.**  A MUD can be quiet for minutes, so
silence proves nothing, and a router rebooting or a laptop lid closing leaves
the read waiting for ever: the client says "connected" while 3K has long since
made you link-dead, and the reconnect that exists for exactly this never
starts.  The socket now has TCP keepalive at 30 seconds idle, 10 between
probes, 3 probes -- the system default is two hours -- so no answer becomes an
error the read loop already treats as a drop.  A connect nobody answers gives
up at twenty seconds instead of the operating system's two minutes, during
which Disconnect could not interrupt it.

**Started while 3K is down.**  The first connection failing used to be the
end: the installed client exited before its window opened, so it looked as
though it had never started.  The window comes up now and the client keeps
knocking, as after any link death.

**Another player's text in a command.**  A rule that puts a tell into what it
sends could carry a line break from somebody else, and a line break is a second
command.  `send` turns them into spaces, and doubles `0xFF`, which telnet
reads as the start of a command of its own.  A pasted block from the page goes
out a line at a time, each through the aliases and the rate governor.

**The page's socket.**  Three malformed messages each closed it, taking every
panel with it; a message that cannot be handled is now logged and the socket
carries on.  A frame header's length is checked before anything is read, so
one claiming eight exabytes is refused rather than waited for.  Frames must be
masked, as browsers always do, and a message in pieces is put back together.
A page that stops reading -- a frozen tab, a machine asleep with the window
open -- used to have everything the MUD said queued for it without limit; past
eight megabytes it is dropped, and it reconnects and gets the scrollback.  A
connection has ten seconds to say what it wants, and a header longer than any
browser sends is closed rather than escaping as an unhandled exception.

**DNS rebinding.**  The Origin check stops somebody else's page opening a
socket to us.  A page on somebody's domain that has the domain re-pointed at
127.0.0.1 is same-origin with itself, though, and its requests carry its own
name in `Host` -- so a `Host` that is not this machine is refused too.

**Links.**  Addresses in the output underline on hover and open with
shift-click -- shift, because a plain click is for selecting text.  They go to
the server rather than to `window.open`, which in app mode opens inside the
client's private profile; the server hands them to the player's own browser,
after checking they are http or https with nothing in them that is not part of
an address, because anybody on 3K can put text on this screen.  The release
link in About is held to `https://github.com/` for the same reason: a
`javascript:` address there would run inside the one page that can drive the
character.

**Somebody else's tarball.**  The escape check compared resolved paths with
`startswith`, and `common/bot/../../../out2/f` passed it when unpacking into
`out`, because `out2` starts with `out`.  It wrote a real file.  Names are now
refused as names first -- `..`, backslashes and colons, the last two meaning
something else again on Windows -- and then as places with `is_relative_to`.
Each file and the whole archive have a ceiling once unpacked, not only on the
wire.

**A machine that had never been to GitHub.**  Python checks HTTPS against
the machine's certificate store, and on Windows that store is filled in on
demand: a root arrives the first time a Windows program asks for it, and
Python reading the store is not asking.  A tester's client came up with no
map, no bots and "unable to get local issuer certificate" on the Updates page,
because their machine had never opened GitHub in a browser.  The client now
carries Mozilla's roots, as curl publishes them, in `mud/cacert.pem`, and
trusts them alongside the machine's store rather than instead of it -- a work
proxy or an antivirus that re-signs HTTPS adds its own root to the store, and
that has to keep working.  Checked by running the real update code with the
machine's store emptied: it failed exactly as the tester's did, and with the
bundle it fetched the whole of 3kdb.  `tools/refresh_certs.py` updates it,
against curl's published SHA-256.

**A file half written.**  Rules, routes, characters and the line markers were
written with `write_text`, which truncates first.  A crash between the two left
half a file; half a file loaded as nothing; and the next save wrote the nothing
back.  Fifty triggers became two bytes that way in a test.  They are written
beside the original, flushed, and renamed over it now -- and a file that will
not load is moved aside as `name.unreadable-<time>` rather than treated as
empty.  A key from a newer version is dropped rather than a reason to refuse to
start, which is what a `TypeError` in the loader had made it.

**Background work.**  `asyncio.create_task` keeps only a weak reference, and
an exception in a task nobody awaits goes nowhere.  Everything started in the
background goes through `events.spawn` now, which holds it until it finishes
and writes any failure to the console or `client.log`.

What was measured and left alone: every MIP code with 78,000 random payloads,
and ten thousand mutated chunks of real captures through the whole inbound
path, raised nothing.  The read loop is guarded anyway, because everything
hangs off it and the next surprise should cost one chunk rather than the
session.

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

    dankclient\
      python\         the interpreter, pinned to a version and a hash
      mud\            the client
      dankclient.cmd          start it
      dankclient-console.cmd  ...keeping the console, for when it does not start

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
-- goes to `%LOCALAPPDATA%\dankclient` rather than beside the program, because an
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

**`RemoveExistingProducts` goes after `InstallFinalize`, not before.**  0.2.0
upgraded over 0.1.0 into an install with no interpreter in it, and the reason
is worth writing down.  Component ids are a hash of the file path, so a new
version shares them with the old one; file costing runs at sequence 1000, five
hundred before the old product was being removed at 1501.  Costing saw
`python\pythonw.exe` already on disk under the same component, byte for byte
the same file, and decided there was no work to do.  The removal then deleted
it and `InstallFiles` never put it back.  Scheduled late, the new files go down
first and each shared component's reference count reaches two, so removing the
old product only takes it back to one and the files stay.  It also fails the
better way round: a failed install leaves the working older one in place.

Three pieces of bookkeeping make an upgrade an upgrade rather than a second
copy.  The upgrade code is pinned and must never change: Windows matches
versions by it, and a changed one installs 0.2.0 beside 0.1.0 with neither
aware of the other.  Component GUIDs are derived from the file path rather than
generated, so two builds of the same file agree and an upgrade replaces it
instead of leaving both.  And `RemoveExistingProducts` runs after
`InstallFinalize`, for the reason above.

Your map and characters survive all of that, because they were never in the
program folder: `%LOCALAPPDATA%\dankclient` is a different place, and the
installer has no reason to touch it.

It carries an icon.  Windows shows a generic executable box for anything
without one -- in the Start Menu, on the taskbar, in Apps & Features -- and a
program that looks like every other unlabelled program is one people lose.  The
mark is the map panel at icon size: four rooms, and the one you are standing in
lit.  `tools/make_icon.py` draws it at seven sizes with nothing but zlib, four
times over and averaged down, which is what gives the corners their curve.

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

Typed in the browser or the console; they never reach the MUD.  **Options ->
Commands** lists them grouped by what you are trying to do, which is where
somebody who does not already know that `/help` exists will find them; clicking
one loads it into the input box, because most of them take an argument.

    /help  /state  /clock  /find <text>            what happened, and where
    /here  /bind <where>  /lost  /go <name>        where you are, and getting
    /marks [text]  /region <name>  /regions        about
    /name  /merge <id>  /forget <id>  /new         correcting the map
    /dupes  /repair  /lock  /unlock
    /bots  /stop  /prefixes [set]                  what is driving the
    /scripts  /reload  /test <line>  /triggers     character, and scripting
