# Paths and steppers

A path is a walk: the steps, and optionally creatures to kill along it. A stepper walks one for you, one room at a time, and pauses when you step away from the keyboard.

## Making a path

[Options → Paths & steppers](options:routes), **+ New path**.

- **Steps**: separated by spaces, commas, semicolons or new lines. `3n` repeats a step. Anything that is not a direction is sent as a command, so `climb pipe` works. Wrap a step in braces to keep it together: `{pick fruit;get seed;d}`.
- **Start room**: a room number to walk to first. The client checks it arrived; blank starts wherever you are.
- **Before starting**: commands sent once, one per line, e.g. `touch angel rune`.
- **Attack on sight**: names, or any word from their long description, separated by commas. Blank walks without fighting.
- **Repeat**, and **Rest** (seconds in each room).

- **Folder**: optional, and it changes nothing about the walk. A `/` makes
  another level, so `chaos/dungeon` puts the path in **dungeon** inside
  **chaos**, and the triangle on a folder's heading folds it away. Naming a
  folder is how you make one, and it exists only while something is in it.
  **Rename** renames the folders under it too; clearing the name puts them
  back at the top. Up to five levels.

A folder is shared with your triggers and aliases: give this path and that
area's rules the same folder name and [Options → Folders](options:folders)
shows them together, with one switch. A path in a folder that is switched off
will not walk until it is switched back on.

3kdb's hundred-odd paths come in through [Options → Updates](options:updates).
Those arrive filed under 3kdb's own tags, so 67 of them start in **chaos** and
**chaos/dungeon** and the rest at the top, for you to file as you like.

## Walking one

In the **Stepper panel**, type part of a path's name, a step or a creature, and press **Start** beside it. Clicking the name only picks it.

- **Pause** stops and remembers where. **Resume** walks back there and carries on.
- **Stop** stops, forgets where it was, and empties the panel. When nothing is running, the same button is **Clear**.
- **AutoCollect** sends `get all` in a room once its fights are over, before moving on.
- **Loop** starts the path over when it reaches the end. It is the path's own **Repeat**, so ticking it here ticks it there. Unticked while walking, the stepper finishes the lap it is on.
- **COT when done**: when a path finishes by itself and is not looping, walk to the Center of Town, as `/go cot` does. Not after **Stop** or **Pause**, and not when a stepper gives up partway.

## How it fights

In each room it kills one target at a time. After every kill it glances, and moves on only when the glance shows the room clear. A fight has no time limit. A creature that will not start a fight at all is skipped for that room.

**Other players.** In a room with something to kill and another player in it, a stepper fights only if everybody else there is in your party. A player who is not is somebody else's hunt: the stepper leaves that room's creatures alone and moves on. It learns your party from 3K's `[PARTY]` joins, quits and boots, and from `pwho`, which it sends when a player it does not know is in a room with something to fight.

## Stay at the keyboard

3K expects a person to be playing. **The deadman** keeps a stepper to that: if you type nothing for 15 minutes, steppers pause and nothing automated is sent until you type again. The 15 minutes is fixed: it cannot be changed or turned off.

- `/stop` stops every stepper, empties the queue, and drops any rule that is waiting.
- `/steppers` lists what is running.
