// The Guild panel: 3Scapes' Guild.* packages, one tab each, under the
// MUD's own field names.  Everything here is a real payload from a live
// gentech session.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const p = page({
  guildpanel: 'section', 'guild-name': 'span',
  'guild-tabs': 'div', 'guild-rows': 'div',
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

renderGuilds({});
check('and it goes away again when the feed does',
  el('guildpanel').hidden === true);

finish();
