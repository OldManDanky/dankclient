// The folder tree: nesting, counts, folding, and that nothing is ever hidden
// by accident.
'use strict';

const { page, load, check, same, finish } = require('./stage');

page({});
load('folders.js');

const items = [
  { name: 'a', group: 'chaos' },
  { name: 'b', group: 'chaos/dungeon' },
  { name: 'c', group: 'chaos/dungeon' },
  { name: 'd', group: '' },
  { name: 'e', group: 'elsewhere' },
];

function draw(extra) {
  return folderTree(Object.assign({
    key: 'test',
    items: items,
    folderOf: (i) => i.group,
    card: (i) => {
      const el = document.createElement('div');
      el.className = 'route';
      el.textContent = i.name;
      return el;
    },
  }, extra || {}));
}

const out = draw();
const names = out.map((el) => el.className === 'folder'
  ? 'FOLDER ' + el.querySelector('b').textContent
  : el.textContent);

// `same` returns a boolean; it is not an assertion on its own.
check('folders sort, then what is filed in them, then the loose ones',
      same(names, ['FOLDER chaos', 'FOLDER dungeon', 'b', 'c', 'a',
                   'FOLDER elsewhere', 'e', 'd']), names.join(' '));

const chaos = out[0];
check('a folder counts everything beneath it, not just its own',
      chaos.querySelector('.n').textContent === '3 items',
      chaos.querySelector('.n').textContent);
check('a folder holding one says so in the singular',
      out.find((e) => e.className === 'folder'
               && e.querySelector('b').textContent === 'elsewhere')
        .querySelector('.n').textContent === '1 item');

// Depth: the heading is indented, and what is filed under it one further.
check('a nested folder is indented', out[1].style.getPropertyValue('--depth') === '1',
      out[1].style.getPropertyValue('--depth'));
check('a filed item is marked as filed', out[2].classList.contains('filed'));
check('a loose item is not', !out[7].classList.contains('filed'));

// Folding: clicking the twist hides what is under it and nothing else.
let redrawn = 0;
const first = draw({ redraw: () => { redrawn += 1; } });
first[0].querySelector('.twist').onclick();
check('folding asks for a redraw', redrawn === 1);
const after = draw();
const left = after.map((el) => el.className === 'folder'
  ? 'FOLDER ' + el.querySelector('b').textContent : el.textContent);
check('a folded folder keeps its own heading and hides what is under it',
      same(left, ['FOLDER chaos', 'FOLDER elsewhere', 'e', 'd']),
      left.join(' '));
check('and its count still says what is in there',
      after[0].querySelector('.n').textContent === '3 items');

// A caller may measure its folders its own way -- rules count what is on.
// Its own list key: the fold above is remembered for 'test' now, and these
// two are about headings rather than folding.
const counted = draw({ key: 'test-count', count: (node, n) => `${n} on` });
check('the count text is the caller’s when it gives one',
      counted[0].querySelector('.n').textContent === '3 on');

// A caller's own folder action is appended to the heading.
const acted = draw({
  key: 'test-actions',
  actions: (node) => {
    const b = document.createElement('button');
    b.textContent = 'turn off ' + node.path;
    return [b];
  },
});
// textContent on a parent does not gather its children in the stand-in DOM,
// so look at the button itself.
const said = (el) => el.children.filter((c) => c.tagName === 'button')
  .map((c) => c.textContent);
check('a folder-wide action reaches the heading',
      said(acted[0]).includes('turn off chaos'), said(acted[0]));
check('and a nested one gets its whole path',
      said(acted[1]).includes('turn off chaos/dungeon'), said(acted[1]));

finish();
