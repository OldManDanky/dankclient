# Patterns and regex

How the **Match** box decides whether a line is the one you mean, and how to pick pieces out of it to use in what the rule sends.

## The four kinds

| Match | Fires when | Pieces you can use |
|---|---|---|
| **contains** | the text appears anywhere in the line | none |
| **glob** | the text is found in the line, with `*` standing for anything | each `*` is `{1}`, `{2}`... |
| **regex** | a regular expression is found in the line | each `( )` is `{1}`, `{2}`... |
| **command** | the first word you type is this word (aliases) | `{args}`, `{1}`, `{2}`... |

All of them care about capitals, except **command**. Start with **contains**; move to **glob** or **regex** when you need a piece of the line.

## Glob

`*` means "anything here". Like **contains**, it can be found anywhere in the line.

- `* tells you: *` matches `Someone tells you: hi`, with `{1}` = `Someone` and `{2}` = `hi`.
- A `*` at the start takes everything before the rest, so on a line that begins with something else, `{1}` has that too. When that matters, use a regex.

## Regex

A regex is found anywhere in the line unless you anchor it. The pieces that matter most:

| Write | It matches |
|---|---|
| `\w+` | one word: letters, digits, `_` |
| `\d+` | a number |
| `\s+` | one or more spaces |
| `.*` | anything, including nothing |
| `.` | any single character |
| `^` | the start of the line |
| `$` | the end of the line |
| `(...)` | the same, and keeps it as `{1}`, `{2}`... |
| `(?P<who>...)` | keeps it by name, as `{who}` |
| `(this\|that)` | either one |
| `\.` `\(` `\?` `\*` | a real `.` `(` `?` `*` |
| `(?i)` at the very start | ignore capitals |

Use numbers or names in one rule, not both: once a pattern has a named piece, only the names are kept.

## Worked examples

**A tell.** `Someone tells you: are you there?`

- Pattern: `^(\w+) tells you: (.*)`
- `{1}` is `Someone`, `{2}` is `are you there?`

**The other way out.** `    There are two obvious exits: light, turnaway`

- Pattern: `There are two obvious exits: light, (\w+)`, send `{1}`
- This line starts with spaces, so `^There` would not match it.
- 3K lists exits in its own order. To catch `light` first or second: `There are two obvious exits: (?=.*\blight\b)(?:light, )?(?!light\b)(\w+)`

**A number.** `You have 1234 gold coins.` Pattern `You have (\d+) gold`, and `{1}` is `1234`.

## Coming from TinTin++

The client does not read TinTin++'s `%` codes. Write them like this:

| TinTin++ | Here, with **regex** |
|---|---|
| `%w` | `(\w+)` |
| `%d` | `(\d+)` |
| `%*` | `(.*)` |
| `%s` / `%S` | `\s+` / `\S+` |
| `{this\|that}` | `(this\|that)` |
| `%1` in what it sends | `{1}` |
| `^` and `$` | the same |

So `There are two obvious exits: light, (%w)` sending `%1` becomes `There are two obvious exits: light, (\w+)` sending `{1}`.

## When it does not fire

- Try the line in **Try a line**, at the bottom of the triggers page.
- Check capitals: `rat` does not match `Rat`. Add `(?i)` to a regex to ignore them.
- Check spaces: 3K pads some lines, and starts some with spaces.
- In a regex, `.`, `(`, `)`, `?`, `*`, `+`, `[` and `|` mean something. Put `\` in front for the real character.
