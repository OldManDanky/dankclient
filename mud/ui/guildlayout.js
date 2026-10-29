/* How one guild's packages are grouped into tabs.

   The panel knows no guild, and that stays true: this file is a table, not
   code, and the renderer works the same with it or without it.  A guild
   named here gets its packages gathered into tabs that mean something --
   everything about trade on one tab rather than four tabs apart -- and a
   guild not named here gets a tab per package exactly as before.

   Grouping PACKAGES rather than fields is the deliberate limit.  Naming
   every field is where a per-guild panel turns into thousands of lines
   nobody can keep up to date, and it is also where it starts being wrong:
   a label invented here outlives the day the MUD changes what it sends.
   Grouping packages costs a dozen lines, needs no field to be understood,
   and gets most of the benefit.

   Nothing can be hidden by this file.  A package not mentioned in any tab
   is collected onto a last tab of its own, so a guild that starts sending
   something new shows it the day it arrives rather than the day somebody
   remembers to add it here. */

(function () {
  window.GUILD_LAYOUTS = {
    // The guild names itself in every package it sends; this is matched
    // against that, lowercased.
    viking: [
      { title: 'Status', packages: ['Guild.State', 'Guild.Info'] },
      { title: 'City', packages: ['Guild.City', 'Guild.CityBuildings'] },
      { title: 'Settlement', packages: ['Guild.Settlement'] },
      { title: 'Trade', packages: ['Guild.Trade', 'Guild.TradeQueue',
                                   'Guild.TradeGoods', 'Guild.Warehouse'] },
      { title: 'People', packages: ['Guild.Roster'] },
      { title: 'Livestock', packages: ['Guild.Livestock',
                                       'Guild.LivestockMarket'] },
      { title: 'Fleet', packages: ['Guild.Fleet', 'Guild.Voyage'] },
      { title: 'Kingdom', packages: ['Guild.Kingdom', 'Guild.War'] },
      { title: 'Map', packages: ['Guild.Map'] },
    ],
  };
}());
