# Triggers

A trigger watches the lines 3K sends, and when one matches, it does something: sends a command, shows a note, waits, or runs a client command.

## Making one

1. Open [Options → Triggers](options:trigger) and press **+ New trigger**.
2. **Match**: how the text is compared. Start with **contains**; see [Patterns and regex](#patterns) for the others.
3. **Text**: what to look for, e.g. `arrives.`
4. **Then**: what to do. Leave it as **send to MUD** and type the command, e.g. `kill rat`. **+ action** adds another. See [What a rule can do](#actions).
5. **Save**.

## The other boxes

- **Name**: optional, for the list.
- **Group**: optional. Rules with the same group are switched on and off together. See [Groups and modes](#groups).
- **Speed**: **normal** waits its turn when you are near 3K's command limit (APM). **immediate** goes at once, whatever the limit. **one per combat round** sends on the next round.
- **enabled**: untick to keep the trigger but stop it firing.
- **stop after this**: no trigger after this one sees the line.
- **gag**: keep the line off the screen. Other rules and the log still see it.

## What a trigger sees

Each line as it appears on screen, without its colours: `Someone tells you: hi`, not the colour codes around it. Some 3K lines start with spaces (the exits line does), and that matters if your pattern uses `^`.

A trigger fires every time its line appears, including when you `look` again.

## Testing

The **Try a line** box at the bottom of the page runs a line through your triggers and aliases without sending anything, and says which matched and what they captured. `/test <line>` does the same from the command box.

## Examples

| When 3K says | Match | Text | Then |
|---|---|---|---|
| `A rat arrives.` | contains | `rat arrives` | send `kill rat` |
| `Someone tells you: hi` | regex | `^(\w+) tells you: ` | send `tell {1} back soon` |
| `You are hungry.` | contains | `You are hungry` | send `eat bread` |

**Show as Python**, in the form, shows the same trigger as a script, if you ever want to take it further. See [Python scripts](#scripts).
