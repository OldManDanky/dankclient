# Python scripts

Anything the rules cannot do, a script can. Scripts are Python files in the `scripts` folder in your data folder, and are reloaded as you save them.

```
@trigger(r"(?P<who>\w+) tells you: help")
def _(m):
    send(f"tell {m['who']} on my way")

@when(lambda p: p.hp_pct and p.hp_pct < 35)
def _():
    send("flee", PANIC)
```

The easiest start: make the rule in Options, press **Show as Python**, and copy it into a file. [Options → Script files](options:scripts) lists the rules your scripts made; `/scripts` shows what is loaded and any errors, and `/reload` rescans the folder.
