# GMCP on 3Scapes

3Scapes sends structured data alongside the game text -- your vitals, the room you are in, your guild's state -- over a second protocol called GMCP. There is nothing to switch on: the client agrees to it as it connects, asks for everything 3Scapes offers, and uses it. Three Kingdoms does not send any of it, and nothing here applies there.

## What it changes for you

- **The map is told where you are.** 3Scapes names each room by number as you walk into it, so the map never has to work out which room this is from what it looks like. It cannot lose you, and it cannot file one room under two names.
- **The map fills in faster than you walk.** Each room also names where its exits go, so those become ways on the map without anyone walking them.
- **The Guild panel.** Everything 3Scapes says about your guild, a tab per package. See below.
- Your health, spell points and guild points still come from MIP, the protocol both MUDs speak, so the vitals strip reads the same on either game.

## The Guild panel

3Scapes sends a great deal about your guild -- seven packages on some guilds, dozens of numbers each. The panel sits in the sidebar, directly under **Session**, and puts each package on its own tab: **State**, **Systems**, **Info**, **Progress**, **Stats**, **Config**, **Powers**, or whichever of them your guild sends. Click its heading to roll it up out of the way, and again to bring it back.

The names on the rows are **your guild's own**, exactly as the MUD sends them. They are not translated, because every guild's are different and a friendlier name invented here could easily be the wrong one -- these are the names you already read in the game. Where the shape of a name says something, the panel uses it: a count with a ceiling is shown as a pair, something measured in seconds becomes a countdown, a percentage gets its sign, and a switch reads **on** or **off**. A number at zero is drawn quieter so the ones that matter stand out.

The panel appears only when something has arrived, so it is absent on Three Kingdoms. [Options → Layout](options:panels) hides it altogether if you would rather not have it.

Your guild is also shown on the character screen, beside the MUD and the profession. Nobody types it: the client reads it from the feed the first time you play and remembers it.

## When it is not working

`/gmcp` says what is going on, which is worth knowing because a feed that is silent looks the same however it failed:

- whether the MUD offered GMCP at all, and whether the client agreed;
- what the client asked for, and under which spelling;
- what the MUD answered -- the packages it will send you, and the ones it offers but was not asked for;
- every package that has actually arrived, with a count, its field names and its last message;
- and anything that arrived without being offered, because the MUD's list of what it sends is not complete.

A quiet feed is usually just a quiet moment: packages are sent when something changes and not otherwise. Room data comes when you **enter** a room -- `look` does not send it again.
