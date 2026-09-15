# Professions

Pick a character's first profession on the character screen and 3kdb's commands for it load whenever you play that character.

## Choosing one

Open the character screen from the sidebar, press **Edit** on a character and choose a **Profession**. It is the first one `profs` lists. Play the character, or save while you are playing them, and a line in the output says what has loaded. If `profs` names a different profession, the client says so.

Only one loads at a time, and none loads for a character with **None**.

## What each one adds

These are 3kdb's modules written again for this client, under 3kdb's names.

- **Golem Master**: `build_golem <kind>` golemizes the head, torso and limbs from the next three corpses and builds the golem; an expired golem is rebuilt as the same kind. `fill_golem` gives it preservations until it is full.
- **Herbologist**: says how long each herb lasted when it wears off. `.herbs` lists what each one does.
- **Marshal**: counts the standard's charges (`.standard`). `.rallycry offensive on` uses that rallycry once a fight, between rounds 7 and 15, while there are charges; `defensive`, `heal` and `spirit` work the same way. All four start off.
- **Reforger**: `ref <item> <type>` reforges to defense from the largest amount down; `refg` does it on the ground. `refk`, `refs`, `refk1` and `refk2` are 3kdb's knife and sword runs.
- **Transmuter**: `transmute_burn consolidate`, `consolidate-leg`, `train` or `train-leg` reads your satchel and transmutes it; `transmute_burn2 superior` or `legendary` does each item all at once; `transmute_ug <item> <quality>` lifts one lot; `transmute_ratios` and `transmuter-stats` show the numbers.
- **Trapper**: looking in your rucksack draws one table of traps and materials instead of five lines, and `.traps` draws it again. `.scrounge <item>` tries metal, wood and hide in turn; `.scrounge-pref`, `.scrounge+ <material>` and `.scrounge- <material>` change the order, which is kept with the character.

A burn sends a lot of commands at once, and the APM warning may say so. Moving never counts.

## Also load: corpse counts, crafting and kill stats

3kdb loads these whatever your profession, so the character screen has a tick box for each under **Also load**.

- **Corpse counts** follow corpses into and out of your coffin, Death's freezer, the tech ultra-cooler, a golem or packmule, a priest's aerial servant, your inventory and what you smuggle, and put the total in the Combat tracking panel. An inventory, or a look inside one of those, sets the count outright. `.corpses` shows where they are, `.corpses check` looks in your inventory, and `corpse_select` uses the next one: coffin, freezer, cooler, golem or servant, inventory, and what you smuggle last.
- **Crafting helpers**: `assembler` reads your satchel and assembles every five of a kind; `autosmelt <ore>` smelts it until there is none left, and `autosmelt off` stops; `forge-on` fills and fires each moulding you examine until `forge-off`; `fill-moulding` fills one with your best materials. `make-gem <gem>` takes the legendary materials from your satchel, walks to the enchanter's shop and kiln, and makes it. `gem-lookup <word or level>` and `jewel-lookup <word or level>` look recipes up, and `borrow-tomes`, `buy-tomes` and `box-tomes` get all six tomes of a volume.
- **Kill stats** notice each kill by 3K's *dealt the killing blow* line, however the creature died, and keep who killed it, how many rounds and how long it took, the damage you dealt and took (3K's numbers, before your defenses -- without 3K's numbers setting those columns are left out), and the xp and coins it gave, which it asks 3K for with `xp` and `coins` and keeps off the screen. `.kills` shows the last fifteen with totals, a kill's average and the rates an hour; `.kills 40` shows more, `.kills <mob>` only those, `.kills clear` starts again, and `.kills ask off` stops the questions. 3kdb's `3kReport` and `3kReport-clear` work too. The kill count, xp an hour, the average rounds and damage a round, and the last kill sit in the Combat tracking panel, below the Stepper; its **reset** clears them all.

A profession loads like a [Python script](#scripts), so a script of your own can do anything these do not.
