# Groups and modes

A group is a name you give several rules so they can be switched on and off together, like TinTin++'s classes.

## Putting rules in a group

In any trigger, alias, event, stat watch or timer, type a name in **Group**, such as `party`. Every rule with that name is in the group. The list in Options shows each group under its own heading.

## Switching

- `/group party off` and `/group party on`, from the command box.
- Or the **turn off** / **turn on** button on the group's heading in Options.
- `/group party` lists what is in it; `/groups` lists every group and how many are on.

Switching a group switches each rule's own **enabled** box, so it is remembered, and you can still switch one rule by itself.

## Modes

Put your party triggers in `party` and your solo ones in `solo`, then make two aliases:

- `/alias partymode /group solo off;/group party on`
- `/alias solomode /group party off;/group solo on`

Now `partymode` and `solomode` swap them over.
