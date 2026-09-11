# Routes and bots

A route is a walk: a path, and optionally creatures to kill along it. Running one is a bot.

## Making a route

[Options → Routes & bots](options:routes), **+ New route**.

- **Path**: the steps, separated by spaces, commas, semicolons or new lines. `3n` repeats a step. Anything that is not a direction is sent as a command, so `climb pipe` works. Wrap a step in braces to keep it together: `{pick fruit;get seed;d}`.
- **Start room**: a room number to walk to first. The client checks it arrived; blank starts wherever you are.
- **Before starting**: commands sent once, one per line, e.g. `touch angel rune`.
- **Attack on sight**: names, or any word from their long description, separated by commas. Blank walks without fighting.
- **Repeat**, **Other players** (wait rather than take their kill), and **Rest** (seconds in each room).

3kdb's hundred-odd routes come in through [Options → Updates](options:updates).

## Running one

In the **Bot panel**, type part of a route's name, a step or a creature, and press **Start** beside it. Clicking the name only picks it.

- **Pause** stops and remembers where. **Resume** walks back there and carries on.
- **Stop** stops, forgets where it was, and empties the panel. When nothing is running, the same button is **Clear**.
- **AutoCollect** sends `get all` in a room once its fights are over, before moving on.

## How it fights

In each room it kills one target at a time. After every kill it glances, and moves on only when the glance shows the room clear. A fight has no time limit. A creature that will not start a fight at all is skipped for that room.

## Stopping everything

- `/stop` stops every bot, empties the queue, and drops any rule that is waiting.
- `/bots` lists what is running.
- **The deadman**: if you type nothing for 15 minutes, bots pause and nothing automated is sent until you type again. Set the minutes, or 0 for never, at the top of Routes & bots.
