// The Combat tracking panel: a block for each pack, from what it says.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const p = page({ trackpanel: 'section', 'pack-status': 'div', 'track-sum': 'span' }, {});
load('tracking.js');
const el = (id) => p.els[id];
const text = (node) => node.textContent;

renderTracking([]);
check('nothing loaded, no panel', el('trackpanel').hidden === true);

renderTracking([
  { label: 'Kills', value: '12', note: '1.2M xp/hr',
    rows: [['Last', 'Cur', ['3 rounds', '9,161 dealt', '1.1K xp']]] },
  { label: 'Corpses', value: '8', chips: [['coffin', '7'], ['freezer', '1']] },
]);
const blocks = el('pack-status').children;
check('a block for each pack, and the panel shows', blocks.length === 2 && el('trackpanel').hidden === false);

const [head, value, row] = blocks[0].children;
check('the label and the rate share the top line',
  same(head.children.map((c) => [c.className, text(c)]),
    [['trk-label', 'Kills'], ['trk-note', '1.2M xp/hr']]), head.children.map(text));
check('the count is the big number', value.className === 'trk-value' && text(value) === '12');
check('the last kill names the creature, with its details quieter beneath',
  text(row.children[0]) === 'Last' && text(row.children[1]) === 'Cur'
  && same(row.children[2].children.map(text), ['3 rounds', '9,161 dealt', '1.1K xp']));

const chips = blocks[1].children[2].children;
check('corpses are chips, a name and a number each',
  same(chips.map((c) => c.children.map(text)), [['coffin', '7'], ['freezer', '1']]));

check('rolled up, the heading keeps the counts', text(el('track-sum')) === 'Kills 12  ·  Corpses 8',
  text(el('track-sum')));

renderTracking([{ label: 'Kills', value: '0', note: '' }]);
const [, zero] = el('pack-status').children[0].children;
check('a count of nothing is drawn quieter', zero.className === 'trk-value zero'
  && el('pack-status').children[0].children.length === 2, zero.className);

renderTracking(['an older pack says a line']);
check('a pack that says a line of text still shows',
  text(el('pack-status').children[0].children[0]) === 'an older pack says a line');

finish();
