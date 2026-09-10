# Dank Mud Client

A MUD client for [3Kingdoms](https://3k.org), built around MIP -- the
protocol 3K already speaks.  Health, guild state, room contents, tells and
channels arrive as data rather than text to be scraped, and it comes with
the whole 3K map and a library of bots.

## Installing

1. Download **`dankclient-<version>.msi`** from the
   [latest release](https://github.com/OldManDanky/dankclient/releases/latest).
2. Run it.  It installs for you alone, so there is no administrator prompt.
3. Start **Dank Mud Client** from the Start Menu.

Windows 10 or 11.  It opens in a window of its own, drawn by Edge (which
every copy of Windows 10 and 11 has) or Chrome -- you do not need a browser
open, and it does not appear as a tab.

**"Windows protected your PC"**: the installer is not code-signed yet, so
SmartScreen does not recognise it.  Click **More info**, then **Run anyway**.

## The first time you run it

It fetches the map and the bots from
[3kdb](https://github.com/jmitchell33/3kdb) in the background -- about ten
seconds, and you can log in while it runs.

The character screen comes up.  Add your character; the password is optional.
If you save one it is kept on your own machine, in a file only your account
can read, and it is never written to the logs.

## Playing

The three buttons above the map are the ones you will use most:

- **Options** -- routes and bots, triggers, aliases and timers; layout, fonts,
  keyboard and sounds; your character's 3K settings; updates, and a list of
  every client command.  **Find a setting**, at the top, searches all of it.
- **Bots** -- straight to your routes and bots.
- **Disconnect** -- stops the bots, saves everything, and closes the
  connection.  It does **not** send `quit`: you go link-dead, exactly as if
  the line had dropped.  The character screen comes back so you can pick who
  to play next.

Under them, **Session** says who is logged in (click it to switch
character), whether MIP is live, how many commands you have spent this
minute (APM), and the MUD's uptime.  If the connection drops, the reason
shows here first.  The window's title shows the version, and counts tells
that arrive while you are in another window -- "(2) Dank Mud Client" on the
taskbar -- until you come back.

**The Bot panel**, under the map, runs a bot without opening Options.  Type
part of a route's name, a step or a creature it hunts, and press **Start**
beside the one you want (clicking its name just picks it).  **Pause** stops
it and remembers the step it had reached and the room it was in -- even
across closing the client; **Resume** walks you back to that room, deals with
whatever the route hunts there, and carries on from the next step.  **Start
over** begins again from the top, and **Stop** forgets where it had got to.
Only one bot walks at a time from here.  You can hide the panel under
**Options -> Layout -> Show**.

Closing the window does the same as Disconnect, then quits.

If 3K drops you, the client goes back by itself and logs you in again,
waiting a little longer between tries.  The sidebar counts down while it waits.

Commands that start with `/` are for the client and never reach the MUD --
`/help` lists them, and so does **Options -> Commands**.  **Options ->
Marks** lists every place `/go` knows by name -- areas, mobs, shops -- nearest
first, with a **Go** button; `/speedruns` shows the same in the terminal.
Some say *can't reach*: the map has no way in to that area yet, and walking
in once teaches it.  Clicking a room on
the map walks there, and so does `/go <name>`: the whole way goes at once, so
you arrive as fast as 3K can move you, and the Bot panel shows where you are
going.  A route with nothing to fight goes the same way.

In the output, drag to select, double-click for a word or triple-click for a
whole line, then **Ctrl+C** to copy it.  Web addresses underline when you
point at them; **shift-click** opens one in your own browser.  Scrolled up
and more arrives?  **↓ new output** appears at the bottom; click it, or just
send a command, to jump back down.

**Gags** have their own page, **Options -> Gags**.  At the top are yours: type
some text and **Add**, and every line containing it is kept off the screen,
as tt++'s `#gag` does -- `/gag <text>`, `/gags` and `/ungag <text>` do the
same from the command box.  Below them is 3kdb's library, seven hundred-odd
gags in groups -- area monsters, guild combat, items, the ray-gun, blank
lines -- every group off until you switch it on (**Show them** lists a
group's gags first).  It arrives with the map through **Options -> Updates**.
Both are kept for each character, and your triggers and the log still see
every hidden line.  A trigger that does something *and* hides its line stays
a trigger: tick **gag** on it in **Options -> Triggers**.

In the messages window, **right-click** a line to colour it: every line on
that channel, or everything from that person.  Clicking a line still puts a
reply in the command box.  The **mine** tag at the end of the channel tags
hides what you said yourself, so only everybody else's lines are left.

**Dings.**  Right-click a line in the messages window and choose **every ...
line** to hear a ding for that channel (or every tell), or **anything from
...** for that person.  A tell chimes twice, a channel once; your own lines
never ding.  3K's own bell -- what somebody's `wake` sends you -- rings with
three notes.  Volume, test buttons, *only when the window is in the
background* and a switch for the bell are under **Options -> Sounds**.

**Options -> Character setup** has 3K's own `brief` setting -- short or long
room descriptions, and whether 3K draws its minimap -- with a button to send
it and one to ask 3K what it is set to now.  The map follows you in either.

**Trying it out?**  The line markers this client sets stay on your character
if you go back to another client.  Before setting them, press **Save my current
settings** under **Options -> Character setup -> Your own colours**: it reads
your colours from 3K's `ansivars` page and keeps them for that character.
**Put them back** shows exactly what it will send, then sends it on a second
click.  It only touches the settings this client changes.

**Options -> Fonts** sets the terminal's font, size and line spacing, and
the messages window's size.  It offers the fixed-width fonts installed on
your computer, or any other by name.  **Ctrl +** and **Ctrl -** make
everything else bigger or smaller.

**Deadman.**  If you haven't typed a command for 15 minutes, bots and
routes pause where they are and nothing automated is sent -- no triggers, no
timers -- until you type something, and then everything carries on.  Set the
minutes, or 0 for off, at the top of **Options -> Routes & bots**.

To walk with the **numpad**, turn it on under **Options -> Keyboard**:
8 is north, 2 south, 7 north-west and so on, 5 is `look` then `search`, and
`+`/`-` are up and down.  Every key can be set to any command, or several
separated by `;`.  With something typed in the command box the keys type
numbers as usual.

To send the same command over and over, tick **keep the last command in the
box** under **Options -> Keyboard**: it stays there selected, so Enter sends it
again and typing replaces it.

## Updates

**The client**: **Options -> About** says when a newer version is out.
Download the new MSI and run it over the top.  Your map, characters and
settings are kept.

**The map and bots**: **Options -> Updates** checks 3kdb and takes what has
changed.  It only ever adds: rooms you have renamed and routes you have made
are left alone.

## Where your things are

Everything the client keeps is in `%LOCALAPPDATA%\dankclient` -- paste that
into Explorer's address bar.  **Options -> About** shows the same paths.

| | |
|---|---|
| `map.sqlite` | the map, and your session log |
| `profiles\` | your characters and each one's triggers, aliases and timers |
| `scripts\` | Python scripts, if you write any |
| `captures\` | raw recordings of each session |
| `client.log` | what the client said about itself |

Copy that folder to back up.  The program itself is in
`%LOCALAPPDATA%\Programs\Dank Mud Client`, and updating or reinstalling it
does not touch any of the above.

## If it will not start

Look in `%LOCALAPPDATA%\dankclient\client.log` first.  For more,
`dankclient-console.cmd` in the program folder starts it with a console
window that stays open.  Please include either with a
[bug report](https://github.com/OldManDanky/dankclient/issues).

## Uninstalling

**Settings -> Apps -> Installed apps -> Dank Mud Client -> Uninstall.**  This
leaves your map and characters behind in case you come back; delete
`%LOCALAPPDATA%\dankclient` to remove those too.

## Scripting

Triggers, aliases, events, stat watches and timers can all be made in
Options.  For more than that, drop Python into the `scripts` folder; it
reloads as you save.

```python
@on("tell")
def _(t): send(f"tell {t.who} omw")

@when(lambda p: p.hp_pct and p.hp_pct < 35)     # fires on the crossing, once
def _(): send("flee", PANIC)

@trigger(r"(?P<who>\w+) has arrived")
def _(m): log(m["who"])
```

Any rule made in Options can be shown as the equivalent script.
`scripts/_example.py` in this repository shows every hook.

## Running from source

Linux, macOS, or Windows without the installer.  Python 3.12 and nothing
else -- there are no third-party dependencies.

```bash
python3 -m mud --web --app    # a window of its own
python3 -m mud --web          # then open http://127.0.0.1:8080
python3 tests/run.py          # the tests
```

The tests include the browser code, run for real under Node when Node is
installed; without it they say so and the Python tests still run.  Before any
release, one command runs everything -- the tests, a check that no player's
name is in anything to be published, a replay of every recorded session
through the mapper against the last release, and a build of the installer
that is then taken apart and checked:

```bash
python3 tools/release_check.py
```

Building the Windows package, on Linux:

```bash
sudo apt install wixl
python3 tools/build_windows.py --zip   # the program folder, zipped
python3 tools/build_msi.py             # the installer
```

Why it is built the way it is -- the protocol as 3K actually sends it,
mapping with no room ids, reconnecting, the installer -- is in
[docs/DESIGN.md](docs/DESIGN.md).

## Credits and licence

The map and the bots come from
[jmitchell33/3kdb](https://github.com/jmitchell33/3kdb).  The root
certificates in `mud/cacert.pem` are Mozilla's, under the MPL 2.0, as
[extracted by curl](https://curl.se/docs/caextract.html).

GPL-3.0 -- see [LICENSE](LICENSE).
