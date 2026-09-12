// The Folders pane: the census it builds from the two lists the page already
// holds, and what one folder reads like.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const p = page({
  'fold-list': 'div', 'fold-title': 'h4', 'fold-blurb': 'p',
  'fold-back': 'button', 'fold-switch': 'button', 'fold-rename': 'button',
});
const sent = [];
global.ws = { readyState: 1, send: (s) => sent.push(JSON.parse(s)) };
global.options = { count: () => {}, open: () => {}, note: () => {} };

// What the rules and routes panes hold.  The pane owns no data of its own.
global.allRules = () => [
  { id: '1', kind: 'trigger', pattern: 'a zodiac stirs', group: 'zodiacs',
    enabled: true, actions: [{ type: 'send', text: 'say ooh' }] },
  { id: '2', kind: 'alias', pattern: 'zk', group: 'zodiacs', enabled: true,
    actions: [{ type: 'send', text: 'kill it' }, { type: 'send', text: 'get all' }] },
  { id: '3', kind: 'timer', name: 'xp', every: 290, group: 'zodiacs/hunting',
    enabled: false, actions: [{ type: 'send', text: 'xp' }] },
  { id: '4', kind: 'trigger', pattern: 'market', group: 'markets', enabled: true,
    actions: [{ type: 'send', text: 'buy' }] },
  { id: '5', kind: 'trigger', pattern: 'loose', group: '', enabled: true,
    actions: [{ type: 'send', text: 'x' }] },
];
global.allRoutes = () => [
  { id: 'r1', name: 'zodiac circuit', group: 'zodiacs', enabled: true,
    step_count: 12, targets: ['rat'] },
  { id: 'r2', name: 'unfiled', group: '', enabled: true, step_count: 3 },
];

load('folderpane.js');

const rows = () => p.els['fold-list'].querySelectorAll('.fold-row');
const items = () => p.els['fold-list'].querySelectorAll('.fold-item');
const heads = () => p.els['fold-list'].querySelectorAll('.folder')
  .map((e) => e.querySelector('b').textContent);
const textOf = (el) => el.children.map((c) => c.textContent).join(' | ');

renderFolders();

check('only what is in a folder is listed, and every prefix is one',
      same(rows().map((r) => r.querySelector('b').textContent),
           ['markets', 'zodiacs', 'zodiacs/hunting']),
      rows().map((r) => r.querySelector('b').textContent));

const zod = rows().find((r) => r.querySelector('b').textContent === 'zodiacs');
check('a folder says what is in it, by kind, rolling up what is under it',
      textOf(zod).includes('1 trigger') && textOf(zod).includes('1 alias')
      && textOf(zod).includes('1 timer') && textOf(zod).includes('1 route'),
      textOf(zod));
check('and says how many are on when they are not all on',
      textOf(zod).includes('3 of 4 on'), textOf(zod));
check('a singular is a singular, not a stripped plural',
      !textOf(zod).includes('1 rout ') && textOf(zod).includes('1 route'),
      textOf(zod));

// Open it: contents by kind, and what is nested shown as a folder again.
zod.onclick();
check('the title becomes the folder', p.els['fold-title'].textContent === 'zodiacs');
check('its contents are grouped by kind, routes among them',
      same(heads(), ['Triggers (1)', 'Aliases (1)', 'Routes (1)', 'In here']),
      heads());
check('only what is directly in it is listed as items', items().length === 3,
      items().length);
check('the nested folder appears as a folder, not as its contents',
      rows().length === 1
      && rows()[0].querySelector('b').textContent === 'zodiacs/hunting',
      rows().map((r) => r.querySelector('b').textContent));

const said = items().map(textOf);
check('a rule whose title is its pattern does not print it twice',
      said[0].includes('say ooh') && said[0].split('a zodiac stirs').length === 2,
      said[0]);
check('a rule with more than one action says how many more',
      said[1].includes('+1 more'), said[1]);
check('a route says its steps and what it kills',
      said[2].includes('12 steps') && said[2].includes('kills rat'), said[2]);

// The switch is a write, so it goes to the server -- for the folder, not the
// one item, and for everything under it.
sent.length = 0;
p.els['fold-switch'].onclick({ stopPropagation: () => {} });
check('switching sends the folder and what it should become',
      same(sent, [{ t: 'folders', op: 'set', name: 'zodiacs', on: true }]), sent);

// Back to the list.
p.els['fold-back'].onclick();
check('back shows the folders again',
      p.els['fold-title'].textContent === 'Folders' && rows().length === 3);

finish();
