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

- **Options** -- triggers, aliases, timers, bots, panels, updates, and a list
  of every client command.
- **Bots** -- straight to your routes and bots.
- **Disconnect** -- stops the bots, saves everything, and closes the
  connection.  It does **not** send `quit`: you go link-dead, exactly as if
  the line had dropped.  The character screen comes back so you can pick who
  to play next.

Closing the window does the same as Disconnect, then quits.

If 3K drops you, the client goes back by itself and logs you in again,
waiting a little longer between tries.  The sidebar counts down while it waits.

Commands that start with `/` are for the client and never reach the MUD --
`/help` lists them, and so does **Options -> Commands**.  Clicking a room on
the map walks there.

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
[jmitchell33/3kdb](https://github.com/jmitchell33/3kdb).

GPL-3.0 -- see [LICENSE](LICENSE).
