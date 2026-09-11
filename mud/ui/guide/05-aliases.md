# Aliases

An alias is a word you type that the client turns into something else before it goes to 3K.

## From the command box

- `/alias gk kill {1};glance` makes `gk`. Typing `gk rat` sends `kill rat`, then `glance`.
- Separate commands with `;`. Put `/wait 2` between two of them for a pause.
- `{1}` is the first word you type after the alias, `{2}` the second, and `{args}` everything after it: `/alias ct ctell {args}`, then `ct back in five`.
- `/alias` lists them, `/alias gk` shows one, `/unalias gk` removes it.
- Setting a word again changes what it does.

## From Options

[Options → Aliases](options:alias), **+ New alias**. **Match** is **command** for an ordinary alias: the first word has to be yours, in any capitals, and the rest is `{args}`. The same form as a trigger, the same **Then** list: see [What a rule can do](#actions).

An alias made either way is the same thing: it is kept with your character, and shows in both places.

## Aliases that run client commands

`/alias ksolo /group party off;/group solo on` makes a word that switches your triggers over. See [Groups and modes](#groups).
