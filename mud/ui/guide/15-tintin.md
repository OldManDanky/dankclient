# Coming from TinTin++, zMUD or CMUD

Your aliases, triggers, gags, timers and paths can come across as they are. [Options → From other clients](options:tintin) reads your TinTin++ `.tin` files, or the settings export from zMUD (a text file) or CMUD (an XML file), and shows what each thing in them becomes before anything is added.

## Bringing them in

1. Open [Options → From other clients](options:tintin) and press **Choose files…**.
2. Pick your files, all at once if you like: `aliases.tin`, `actions.tin`, `tickers.tin`, `vars.tin` -- or zMUD's settings export.
3. Look down the list. Everything that comes across is ticked; untick anything you do not want.
4. Press **Import**. Importing the same files again adds nothing twice.

## What comes across

| TinTin++ | Here |
|---|---|
| `#alias {gk} {kill %1;glance}` | an alias; `%1` is `{1}`, `%0` is `{args}` |
| `#action {pattern} {commands}` | a trigger, the pattern translated |
| `#gag {text}` | a gag |
| `#ticker {name} {commands} {seconds}` | a timer |
| `#class {name} {open}` | a group, for everything up to its close |
| `#delay 2 {command}`, last | a wait, then the command |
| `#if {!$idle_flag} {commands}` | just the commands: the deadman does that check |
| `$name`, set by `#var` and never changed | its value |
| `#10 command` | the command ten times |

An alias that uses none of `%0`–`%9` gets what you typed after it added on the end, as TinTin++ does. An alias that calls another of your aliases has that one's commands put in its place. Everything imported goes in its `#class` group, or in **tintin**, so `/group tintin off` switches it all off at once. See [Groups and modes](#groups).

## What does not

Real TinTin++ programming does not come across: `#if` on anything but idle, `#math`, `#list`, `#foreach`, `#regexp`, `#format`, and a `$variable` that changes as it runs. Nor do `#highlight` and `#substitute`, which the client has nothing like yet, or calls into 3kdb itself, such as `corpsetrig+` or `.fly`. Each is listed under **Not brought across**, with the reason. Most can be written as a script: see [Python scripts](#scripts).

## From zMUD

zMUD keeps its settings in a `.mud` file the client cannot read, but it will write them out as text: export your settings from zMUD's settings editor, and pick that file. What changes on the way:

| zMUD | Here |
|---|---|
| `#TRIGGER {pattern} {commands} "class"` | a trigger, in the class's group (`areas|zombies` is `areas/zombies`) |
| `{disable}` on a trigger | brought in switched off |
| `#ALIAS name {commands}` | an alias; `%1` is `{1}`, `%-1` is `{args}` |
| `#WAIT 3000` | a wait of 3 seconds |
| `#T- class`, `#T+ class` | `/group class off`, `/group class on` |
| `#GAG` | the trigger hides its line |
| `.3n2e` in commands | its steps: n, n, n, e, e |
| `#PATH name {…}` | a route; if its moves fit one room only, that is where it starts |
| `#ALARM {*5:00}` | a timer, every 5 minutes |

A zMUD trigger ignores capitals, so an imported one does too. `#CAP`, `#BEEP`, zMUD's slow walking (`#STEP`, `#PAUSE`, `#SLOW`), `#VARIABLE`, `#IF` and `#KEY` do not come across; each is listed with the reason.

**Speedwalking** in the command box -- typing `.3n2e` -- can be switched on under [Options → Keyboard](options:keyboard). `h`, `j`, `k` and `l` are nw, ne, sw and se.

## From CMUD

CMUD exports its settings as an XML file; pick that. Its triggers and aliases speak zMUD's language, so everything above holds, and CMUD says a few things zMUD left to guesswork:

- A class that is switched off in CMUD brings its rules in switched off, and classes inside classes become groups like `areas/zombies`.
- A trigger marked as a regex comes in as that regex; one marked case sensitive keeps capitals.
- An alias with **auto append** gets what you typed after it on the end; one without does not.
- Commands on separate lines are separate commands.

Multi-state triggers, Wait, Loop and Expression triggers, buttons, keys, and rules that belong to one of CMUD's own windows (a Tells window, say) do not come across; each is listed with the reason.
