"""A route, and what to kill along it -- the tt++ botpath, in this client.

Everything here is commented out.  Uncomment, save, and the script reloads
itself; save it again and the old route stops before the new one starts.

    /bots     what is running
    /stop     stop everything and clear the queue
"""

# The short form.  "n n e s w" is the walk; targets are matched against the
# name MIP gives each creature, which is the same name you would type.
#
# patrol("n n e s w", targets=["Cur", "Cancer"], name="tradepost")


# The long form, for when the route needs to think.  Same primitives, written
# out: walk() takes one step and waits to arrive, attack() uses the command
# the MUD itself listed for that creature and waits for the fight to end.
#
# @bot("tradepost")
# async def circuit():
#     while True:
#         for step in "n n e s w".split():
#             if not await walk(step):
#                 log(f"{step} did not go anywhere -- stopping")
#                 return
#             for mob in room.mobs():
#                 if mob.name in {"Cur", "Cancer"}:
#                     await attack(mob)
#             if player.sp_pct and player.sp_pct < 30:
#                 await tick()            # let it come back before moving on


# Both stop themselves below the health floor.  A separate watch is still
# worth having, because fleeing is faster than noticing you should have.
#
# @when(lambda p: p.hp_pct and p.hp_pct < 25)
# async def bail():
#     stop_bots()
#     send("flee", PANIC)
