# Groups and modes

A group is a name you give several rules so they can be switched on and off together, like TinTin++'s classes.

## Putting rules in a group

In any trigger, alias, event, stat watch or timer, type a name in **Group**, such as `party`. Every rule with that name is in the group. The list in Options shows each group under its own heading.

## Folders

A `/` in the name makes a folder inside a folder: `areas/zombies` puts the rule
in **zombies**, inside **areas**. The list shows them as folders you can fold
away with the triangle, which is what keeps a long list readable. Up to five
levels deep.

A folder is nothing but the name on the rules in it, so there is no folder to
make first and none left over to tidy up: naming one is making it, and it is
gone when the last rule leaves it. **Rename** on a folder's heading renames
everything under it too; clearing the name puts them all back at the top
without losing any of them.

Switching a folder switches everything under it, so turning **areas** off
turns `areas/zombies` off as well.

## Seeing one area in one place

[Options → Folders](options:folders) lists every folder you have, whatever is
in it: choose one and it shows that folder's triggers, aliases, events, stat
watches, timers **and routes** together, with one switch for the lot. `/folders`
lists the same from the command box.

So a folder called `zodiacs`, put on that area's triggers, its aliases and its
route, is one thing: one page, and `/group zodiacs off` switches all of it,
routes included. A route that is switched off will not walk until it is on
again, however it is started.

## Switching

- `/group party off` and `/group party on`, from the command box.
- Or the **turn off** / **turn on** button on the group's heading in Options.
- `/group party` lists what is in it; `/groups` lists every group and how many are on; `/folders` lists them as folders, counting the routes.

Switching a group switches each rule's own **enabled** box, so it is remembered, and you can still switch one rule by itself.

## Modes

Put your party triggers in `party` and your solo ones in `solo`, then make two aliases:

- `/alias partymode /group solo off;/group party on`
- `/alias solomode /group party off;/group solo on`

Now `partymode` and `solomode` swap them over.
