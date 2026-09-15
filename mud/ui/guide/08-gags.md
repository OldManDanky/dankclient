# Gags

A gag keeps lines off the screen. Your triggers and the log still see them.

- `/gag <text>` hides every line containing that text, capitals included. `/gags` lists them, `/ungag <text>` brings one back, `/ungag all` all of them.
- [Options → Gags](options:gaglib) shows yours at the top, with **Add**, and 3kdb's library of seven hundred-odd below: monsters, guild combat, items, blank lines. Every library group is off until you switch it on. A line with damage numbers in it -- *You hit Cur 1 time for 9161 damage.*, *Cur hits you for 2537 damage!* -- is never hidden by the library, whatever group is on; a gag of your own still hides it.
- A trigger that does something *and* hides its line stays a trigger: tick **gag** on it.
