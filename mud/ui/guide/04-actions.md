# What a rule can do

Every trigger, alias, event, stat watch and timer ends in the same **Then** list. Each line is one action, done in order.

## The actions

- **send to MUD**: send a command, as if you had typed it.
- **show in client**: put a note in the output, for you only.
- **wait (seconds)**: hold back everything below it for that long. `kill rat`, wait `2`, `get all`. Up to an hour; longer than that is a timer.

## Client commands in an action

A **send** that starts with `/` runs as a client command, exactly as typing it would, and never reaches 3K. So an action can be `/group party off`, `/go bank`, or `/stop`. See [Groups and modes](#groups).

## Putting pieces in

Anything in braces is filled in when the rule fires.

- Pieces of the line or command: `{1}`, `{2}`, `{args}`, or a name like `{who}`. See [Patterns and regex](#patterns).
- Your state, in any rule: `{hp}`, `{max_hp}`, `{hp_pct}`, `{sp}`, `{sp_pct}`, `{gp1}`, `{gp2}`, `{enemy}`, `{enemy_pct}`, `{round}`, `{room}`.

A name the rule does not know is left as it is, braces and all.

## Speed

3K watches how many commands you send in a minute (APM). **normal** sends at once when there is room and waits its turn near the limit. **immediate** goes at once regardless. **one per combat round** waits for the next round. Moving is free, and does not count.

## When nothing goes out

If you have not typed anything for a while, the deadman stops everything automated until you type again. See [Routes and bots](#routes). `/stop` also throws away anything still waiting.
