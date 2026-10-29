# GMCP on 3Scapes

3Scapes sends structured data alongside the game text -- your vitals, the room you are in, your guild's state -- over a second protocol called GMCP. There is nothing to switch on: the client agrees to it as it connects, asks for everything 3Scapes offers, and uses it. Three Kingdoms does not send any of it, and nothing here applies there.

## What it changes for you

- **The map is told where you are.** 3Scapes names each room by number as you walk into it, so the map never has to work out which room this is from what it looks like. It cannot lose you, and it cannot file one room under two names.
- **The map fills in faster than you walk.** Each room also names where its exits go, so those become ways on the map without anyone walking them.
- **The Guild panel.** Everything 3Scapes says about your guild, a tab per package. See below.
- **Your guild can name its own two point pools.** Where it does, the names on the `GP1` and `GP2` gauges change to the guild's own without you typing anything. A name you set yourself still wins -- clearing it goes back to the guild's.
- Your health, spell points and guild points still come from MIP, the protocol both MUDs speak, so the vitals strip reads the same on either game.

## The Guild panel

3Scapes sends a great deal about your guild -- seven packages on some guilds, sixteen on others, dozens of numbers each. The panel sits in the sidebar, directly under **Session**.

Where the client knows how a guild's packages fit together, it gathers them into tabs that mean something: everything about trade on one tab rather than spread across four. A tab holding more than one package names each of them above its own rows. Anything the grouping does not mention is still shown, on a last tab called **Other** -- so a guild that starts sending something new shows it the day it arrives, not the day somebody gets round to it. For a guild with no grouping, each package gets its own tab: **State**, **Systems**, **Info**, **Progress**, **Stats**, **Config**, **Powers**, or whichever of them your guild sends. Past eight of them the tabs become a dropdown instead, so the list of packages does not fill the panel the numbers are there for. Click the heading to roll the whole thing up out of the way, and again to bring it back.

What arrives is not a flat list of numbers, and it is not shown as one. The plain facts come first, then the blocks, then the tables, so what you glance at is at the top rather than below a forty-row list. A record -- your health, your points, a chain -- becomes a small block under its own heading, except where it reads better on one line: a current and a maximum are shown as a pair with the percentage worked out and a bar under it, and a coordinate as two numbers. The bar says how full and nothing about whether full is good, because a pool you want full and a poison you want empty are the same shape and the MUD does not say which it is sending. A list of records -- your ships, your stock, your trade routes -- becomes a table, one line each, and a wide one scrolls rather than widening the sidebar. A column that is blank or zero the whole way down is left out; it appears the day it has something to say.

The names on the rows are **your guild's own**, exactly as the MUD sends them. They are not translated, because every guild's are different and a friendlier name invented here could easily be the wrong one -- these are the names you already read in the game. Where the shape of a name says something, the panel uses it: a count with a ceiling is shown as a pair, something measured in seconds becomes a countdown, a percentage gets its sign, and a switch reads **on** or **off**. A number at zero is drawn quieter so the ones that matter stand out.

### Maps a guild sends

Some guilds send a map -- a world, a territory, a battle board -- as rows of characters. Where one arrives it is **drawn** at the top of its tab rather than listed as rows of text, with your own position marked on it and a key to the characters actually on screen. Nothing about this is specific to any one guild: any package that arrives carrying a grid is drawn the same way, so a guild nobody here has played gets its map for free.

A map can be sent out into **a window of its own** -- the button is on the map's heading. A world seventy columns across is not a sidebar's business, and the window is the same map, drawn from the same feed as it arrives. Closing the window, or the button again, puts it back in the panel.

A board with nothing on it draws nothing. If a guild sends its map in some encoding the panel cannot draw, it says so plainly instead of drawing something wrong.

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

If a guild panel in particular stays empty, the guild may have a command of its own that sends everything again from scratch -- worth looking for in the guild's own help.
