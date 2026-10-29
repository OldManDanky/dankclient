// The Guild panel: 3Scapes' Guild.* packages, one tab each, under the
// MUD's own field names.  Everything here is a real payload from a live
// gentech session.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const p = page({
  guildpanel: 'section', 'guild-name': 'span',
  'guild-tabs': 'div', 'guild-map': 'div', 'guild-rows': 'div',
}, {});
load('guild.js');
const el = (id) => p.els[id];
const text = (node) => node.textContent;
const pairs = () => {
  const kids = el('guild-rows').children;
  const out = [];
  for (let i = 0; i < kids.length; i += 2) {
    out.push([text(kids[i]), kids[i + 1] ? text(kids[i + 1]) : null]);
  }
  return out;
};

renderGuilds({});
check('Three Kingdoms sends none of this, so there is no panel',
  el('guildpanel').hidden === true);

const FEED = {
  'Guild.State': {
    guild: 'gentech', pu: 9393, pu_max: 12000, pu_store: 4215,
    gexp: 421838, g2n_pct: 42, edna_secs: 1620, illuminated: 0,
  },
  'Guild.Systems': {
    guild: 'gentech', hypergen_secs: 2508, tactical_on: 1, synthorg_on: 0,
    tacshield_type: 'adaptive',
  },
  'Guild.Config': {
    guild: 'gentech',
    autoguild: ['efield', 'lsupp', 'meditate', 'health', 'tshift'],
  },
};

renderGuilds(FEED);
check('the panel appears, named for the guild',
  el('guildpanel').hidden === false && text(el('guild-name')) === 'gentech');

const tabs = el('guild-tabs').children;
check('a tab per package, the Guild. dropped from each',
  same(tabs.map(text), ['Config', 'State', 'Systems']), tabs.map(text));
check('the first is the one showing',
  tabs[0].attrs['aria-selected'] === 'true'
  && tabs[1].attrs['aria-selected'] === 'false');

tabs[1].onclick();
check('clicking a tab switches to it',
  el('guild-tabs').children[1].attrs['aria-selected'] === 'true');

const rows = Object.fromEntries(pairs());
check('a ceiling is shown beside its own field, not on a line of its own',
  rows['pu'] === '9,393 / 12,000' && rows['pu_max'] === undefined, rows['pu']);
check('an underscore reads as a space', rows['pu store'] === '4,215');
check('_pct is a percentage', rows['g2n_pct'] === undefined && rows['g2n pct'] === '42%');
check('_secs is a duration', rows['edna secs'] === '27m 0s', rows['edna secs']);
check('a big number is grouped', rows['gexp'] === '421,838');
check('the guild name is not a row of its own', rows['guild'] === undefined);

const zero = el('guild-rows').children;
const at = zero.findIndex((n) => text(n) === 'illuminated');
check('a field at zero is drawn quieter', zero[at + 1].className.includes('off'));

renderGuilds(FEED);
check('a refresh keeps the tab you were on',
  el('guild-tabs').children[1].attrs['aria-selected'] === 'true');

el('guild-tabs').children[2].onclick();
const sys = Object.fromEntries(pairs());
check('_on reads as a switch, both ways',
  sys['tactical on'] === 'on' && sys['synthorg on'] === 'off');
check('a word field is left as the MUD wrote it',
  sys['tacshield type'] === 'adaptive');

el('guild-tabs').children[0].onclick();
const cfg = pairs();
check('a list is joined, and given the width to be read',
  cfg[0][0] === 'autoguild'
  && cfg[0][1] === 'efield, lsupp, meditate, health, tshift'
  && el('guild-rows').children[0].className.includes('wide'), cfg[0]);

/* Not a capture: a shape no feed here has sent.  We have watched one guild,
   and the panel has to survive the ones we have not. */
renderGuilds({ 'Guild.Powers': {
  guild: 'gentech',
  runes: [{ name: 'rune', level: 3 }, { name: 'axe', level: 1 }],
  slots: [4, null, 'open'],
} });
const kids = () => el('guild-rows').children;
const headed = (name) => kids().find(
  (n) => n.className === 'ghead' && text(n) === name);
check('a list of records is a table, not a line of JSON',
  !!headed('runes') && !!kids().find((n) => n.className === 'gtable'));
const trs = kids().find((n) => n.className === 'gtable').children[0].children;
check("its columns are the records' own fields, in the order they came",
  trs[0].children.map(text).join('|') === 'name|level',
  trs[0].children.map(text));
check('and one line per record',
  trs[1].children.map(text).join('|') === 'rune|3'
  && trs[2].children.map(text).join('|') === 'axe|1',
  trs[1].children.map(text));
// A list of plain values is still a list of plain values.
const slot = kids().findIndex((n) => text(n) === 'slots');
check('a hole in a list stays a hole',
  text(kids()[slot + 1]) === '4, , open', text(kids()[slot + 1]));

/* The package NAMES here are measured -- one guild really does send these
   sixteen -- the one field in each is not.  Seven tabs wrap to two rows and
   read fine; sixteen would fill the panel before a number showed. */
const MANY = {};
for (const n of ['Actives', 'Assets', 'Config', 'Focus', 'Info', 'Progress',
  'Skills', 'Spells', 'SpellsAdvanced', 'SpellsDefense', 'SpellsEnhanceHi',
  'SpellsEnhanceLo', 'SpellsOffense', 'SpellsSummon', 'SpellsUtility',
  'State']) {
  MANY[`Guild.${n}`] = { guild: 'mage', mana: 42 };
}
renderGuilds(MANY);
const strip = el('guild-tabs').children;
check('sixteen packages become one dropdown, not sixteen buttons',
  strip.length === 1 && strip[0].tagName === 'select'
  && strip[0].children.length === 16, strip.map((n) => n.tagName));
check('the dropdown names the packages the same way the tabs did',
  text(strip[0].children[0]) === 'Actives'
  && text(strip[0].children[8]) === 'SpellsAdvanced');
check('and it opens on the first package, as the tabs do',
  strip[0].value === 'Guild.Actives');

strip[0].value = 'Guild.SpellsSummon';
strip[0].onchange();
check('picking one shows it, and the dropdown stays on it',
  el('guild-tabs').children[0].value === 'Guild.SpellsSummon'
  && Object.fromEntries(pairs())['mana'] === '42');

renderGuilds(FEED);
check('back under eight packages it is buttons again',
  el('guild-tabs').children[0].tagName === 'button'
  && el('guild-tabs').children.length === 3);

/* The world map, in the shape the MUD's own `vhelp gmcp_packages` states:
   w, h, active, pos{x,y}, legend, enc, terrain, east, south.  Drawn on the
   SHAPE, so the battle board -- same w/h/terrain -- draws the same way. */
const MAP = {
  'Guild.Map': {
    guild: 'vikings', active: 1, w: 4, h: 3,
    pos: { x: 1, y: 2 },
    enc: { terrain: 'glyph' },
    legend: { '.': 'plains', '^': 'mountain', '~': 'sea', '#': 'ice' },
    terrain: ['..^.', '.~~.', '....'],
    east: ['110', '011', '111'],
    south: ['1100', '0011', '0000'],
    landmarks: ['hall', 'wreck'],
  },
};
renderGuilds(MAP);
const art = el('guild-map').children;
check('a package carrying a grid is drawn as one',
  el('guild-map').hidden === false && art[1].tagName === 'pre');
check('the rows the MUD sent are drawn, with you put in at pos',
  text(art[1]) === '..^.\n.~~.\n.@..', JSON.stringify(text(art[1])));
check('the header says how big it is and where you are',
  text(art[0]) === '4\u00d73 — you are at 1,2', text(art[0]));
check('the legend covers the glyphs on screen and not the rest',
  art[2].children.map(text).join('|') === '. plains|^ mountain|~ sea',
  art[2].children.map(text));
const left = Object.fromEntries(pairs());
check('what the drawing says is not repeated as rows underneath',
  left.terrain === undefined && left.east === undefined
  && left.legend === undefined && left.pos === undefined);
check('and what it does not say still is',
  left.landmarks === 'hall, wreck');

/* A real feed numbers its kinds of ground 0..20 rather than keying them
   by the character on the map, so there is nothing to match against and
   the whole key is listed.  Note 0..9 are single characters and look like
   glyphs: what settles it is that none of them is on the map. */
renderGuilds({ 'Guild.Map': Object.assign({}, MAP['Guild.Map'],
  { legend: { 0: 'plains', 1: 'mountain', 9: 'sea', 20: 'ice' } }) });
check('a key numbered rather than drawn is listed whole',
  el('guild-map').children[2].children.map(text).join('|')
  === '0 plains|1 mountain|9 sea|20 ice',
  el('guild-map').children[2].children.map(text));

renderGuilds({ 'Guild.Map': Object.assign({}, MAP['Guild.Map'],
  { enc: { terrain: 'base64' } }) });
check('an encoding we cannot draw says so instead of drawing nonsense',
  text(el('guild-map').children[0]).includes('base64')
  && el('guild-map').children.length === 1);

/* The real no-battle board: `active: 0` AND nothing in it.  Emptiness is
   what is tested, not the flag -- see the live world map below, which
   sends `active: 0` with seventy columns of real ground. */
renderGuilds({ 'Guild.War': { guild: 'viking', active: 0, w: 0, h: 0,
  terrain: [], war_points: 3 } });
check('a board with nothing on it draws nothing, and still lists its fields',
  el('guild-map').hidden === true
  && Object.fromEntries(pairs())['war points'] === '3');

/* Straight off a live feed: `active: 0` because you are not standing on
   the world map, `pos` -1,-1 for the same reason, a key numbered 0..20
   that does not match the letters in the rows, and a real 70-wide map.
   The first version of this panel drew none of it. */
renderGuilds({ 'Guild.Map': {
  guild: 'viking', active: 0, w: 70, h: 35,
  pos: { y: -1, x: -1 },
  enc: { terrain: 'glyph', east: 'glyph', south: 'glyph' },
  legend: { 0: 'unexplored', 1: 'plains', 2: 'forest', 3: 'hills',
            4: 'mountains', 19: 'blocked (impassable edge)' },
  terrain: ['rWWWffhhhhh', '.hhhffhhhhh', '.........ks'],
  east: ['0000111111', '1111111111'],
  south: ['10001111111', '11111111111'],
} });
const live = el('guild-map').children;
check('a live world map draws, though it says active: 0',
  el('guild-map').hidden === false && live[1].tagName === 'pre',
  el('guild-map').hidden);
check('its rows are drawn exactly as they came',
  text(live[1]) === 'rWWWffhhhhh\n.hhhffhhhhh\n.........ks');
check('and being nowhere on it is not a corner of it',
  text(live[0]) === '70\u00d735', text(live[0]));
check('the numbered key is listed, since no key is on the map',
  live[2].children.length === 6, live[2].children.map(text));

/* Straight off the live feed, which is where "this looks like a raw data
   dump" came from: nested records and lists of records, every one of
   which used to print as its JSON. */
renderGuilds({ 'Guild.State': {
  guild: 'viking',
  hp: { cur: 1667, max: 1667, threk: 0, mthrek: 0, delta: 0 },
  sp: { cur: 926, max: 53 },
  bars: { gp1: 12, gp1_max: 40, gp2: 0, gp2_max: 0 },
  chain: { chain: 0, bsdepth: 2 },
  daler: 14230,
} });
const st = () => el('guild-rows').children;
check('a current and a ceiling is one line, not a block of its own',
  text(st()[st().findIndex((n) => text(n) === 'sp') + 1]) === '926 / 53',
  text(st()[st().findIndex((n) => text(n) === 'sp') + 1]));
const barsAt = st().findIndex(
  (n) => n.className === 'ghead' && text(n) === 'bars');
check('a record with more in it becomes a block under its own heading',
  barsAt >= 0 && st()[barsAt + 1].className === 'gsub');
check('and inside the block the usual pairing still applies',
  st()[barsAt + 1].children.map(text).join('|') === 'gp1|12 / 40|gp2|0 / 0',
  st()[barsAt + 1].children.map(text));
check('a plain number is still a plain number',
  text(st()[st().findIndex((n) => text(n) === 'daler') + 1]) === '14,230');
check('and no JSON anywhere in it',
  !st().map(text).join(' ').includes('{'),
  st().map(text).join(' ').slice(0, 80));

/* The warehouse: a list of records where not every record has every
   field, and one field is blank the whole way down. */
renderGuilds({ 'Guild.Warehouse': {
  guild: 'viking', wstock_cap: 200,
  wstock: [{ amount: 20, good: 'ore', pct: 100, note: '', held: 0 },
           { amount: 9, good: 'mead', grade: 'must', pct: 45,
             note: '', held: 0 }],
} });
const wt = el('guild-rows').children
  .find((n) => n.className === 'gtable').children[0];
check('a column a later record adds is picked up',
  wt.children[0].children.map(text).join('|') === 'amount|good|pct|grade',
  wt.children[0].children.map(text));
check('a column blank the whole way down is dropped',
  !wt.children[0].children.map(text).includes('note'));
check('and so is one that is zero the whole way down',
  !wt.children[0].children.map(text).includes('held'));
check('and a record missing one of them leaves that cell empty',
  wt.children[1].children.map(text).join('|') === '20|ore|100%|',
  wt.children[1].children.map(text));

renderGuilds({});
check('and it goes away again when the feed does',
  el('guildpanel').hidden === true);

finish();
