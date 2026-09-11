# Events, stat watches and timers

Three more kinds of rule, for things that are not a line of text. Each has its own page in Options and the same **Then** list as a trigger ([What a rule can do](#actions)).

## Events

[Options → Events](options:event) fires on something MIP tells the client about:

| Event | What you can use |
|---|---|
| tell | `{who}`, `{message}`, `{from_me}` |
| chat | `{channel}`, `{who}`, `{message}`, `{command}` |
| round | `{round}` |
| enemy | `{enemy}` (empty when a fight ends) |
| room | `{short}`, `{exits}`, `{mobs}`, `{players}`, `{items}` |
| connected, disconnected, retrying | `{seconds}` for retrying |

**Only when** adds conditions, e.g. `who is Friend` or `message contains help`. All of them must hold.

## Stat watches

[Options → Stat watches](options:watch) fires when a number crosses a line: `hp_pct < 35`, `enemy_pct < 10`. Tick **only when it first crosses** so it fires once on the way down, not twice every round while you stay there.

## Timers

[Options → Timers](options:timer), or from the command box:

- `/tick 290 xp` sends `xp` every 290 seconds.
- `/ticks` lists them, `/untick xp` stops one, `/untick all` stops them all.
- `/delay 5 quaff heal` sends something once, five seconds from now.

Timers keep 3K's two-second beat, so two seconds is the shortest, and nothing fires until you are logged in and MIP is flowing.
