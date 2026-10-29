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
const odd = Object.fromEntries(pairs());
check('a list of objects is readable, not [object Object]',
  odd['runes'] === '{"name":"rune","level":3}, {"name":"axe","level":1}',
  odd['runes']);
check('a hole in a list stays a hole',
  odd['slots'] === '4, , open', odd['slots']);

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

renderGuilds({ 'Guild.Map': Object.assign({}, MAP['Guild.Map'],
  { enc: { terrain: 'base64' } }) });
check('an encoding we cannot draw says so instead of drawing nonsense',
  text(el('guild-map').children[0]).includes('base64')
  && el('guild-map').children.length === 1);

renderGuilds({ 'Guild.War': { guild: 'vikings', active: 0, w: 4, h: 1,
  terrain: ['....'], war_points: 3 } });
check('a board with nothing on it draws nothing, and still lists its fields',
  el('guild-map').hidden === true
  && Object.fromEntries(pairs())['war points'] === '3');

renderGuilds({});
check('and it goes away again when the feed does',
  el('guildpanel').hidden === true);

finish();
