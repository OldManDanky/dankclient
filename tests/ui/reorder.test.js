// Moving a card in a list: its grip's arrow keys, dragging, and a folder heading.
'use strict';

const { page, load, check, same, finish } = require('./stage');

page({});
load('folders.js');

const items = [
  { id: 'a', name: 'a', group: 'chaos' },
  { id: 'b', name: 'b', group: 'chaos' },
  { id: 'c', name: 'c', group: 'chaos' },
  { id: 'd', name: 'd', group: '' },
];
const moves = [];
function draw(onMove) {
  return folderTree({
    key: 'test',
    items,
    folderOf: (i) => i.group,
    card: () => {
      const el = document.createElement('div');
      el.className = 'route';
      const top = document.createElement('div');
      top.className = 'top';
      el.append(top);
      return el;
    },
    onMove,
  });
}
const isCard = (el) => el.className.split(' ').includes('route');

const out = draw((item, before, folder) => moves.push([item.id, before ? before.id : null, folder]));
const cards = out.filter(isCard);
const grip = (n) => cards[n].querySelector('.grip');
check('every card gets a grip, first in its top row, and can be dragged',
  cards.every((c, n) => grip(n) && c.children[0].children[0] === grip(n) && c.draggable));

const key = (n, k) => {
  const e = { key: k, prevented: false, preventDefault() { this.prevented = true; } };
  grip(n).onkeydown(e);
  return e;
};
key(1, 'ArrowUp');
check('↑ on the second puts it before the first', same(moves.pop(), ['b', 'a', 'chaos']));
key(0, 'ArrowDown');
check('↓ on the first puts it before the third', same(moves.pop(), ['a', 'c', 'chaos']));
key(1, 'ArrowDown');
check('↓ on the one before last makes it last in its folder', same(moves.pop(), ['b', null, 'chaos']));
key(2, 'ArrowDown');
key(0, 'ArrowUp');
check('and nothing moves past either end of its folder', moves.length === 0);

const ev = (y) => ({ clientY: y, prevented: false, preventDefault() { this.prevented = true; },
  dataTransfer: { setData() {}, effectAllowed: '' } });
cards[2].ondragstart(ev(0));                     // pick up c
cards[0].ondragover(ev(10));
check('dragged over the top half of a card, it shows it will land before it',
  cards[0].classList.contains('drop-before') && !cards[0].classList.contains('drop-after'));
cards[0].ondrop(ev(10));
check('and dropped there, it goes before it', same(moves.pop(), ['c', 'a', 'chaos']));
check('the marker goes when it lands', !cards[0].classList.contains('drop-before'));

cards[0].ondragstart(ev(0));                     // pick up a
cards[1].ondrop(ev(100));                        // the bottom half of b
check('dropped on a bottom half, it goes after that card', same(moves.pop(), ['a', 'c', 'chaos']));

cards[3].ondragstart(ev(0));                     // d, from the top level
const heading = out.find((el) => el.className === 'folder');
heading.ondragover(ev(0));
check('a folder heading shows it will take it', heading.classList.contains('drop-into'));
heading.ondrop(ev(0));
check('dropped on a folder heading, it is filed last in that folder',
  same(moves.pop(), ['d', null, 'chaos']));

cards[1].ondragstart(ev(0));
cards[1].ondrop(ev(10));
check('dropped on itself, nothing moves', moves.length === 0);
cards[0].ondragstart(ev(0));                     // a, onto the bottom half of the card before b
cards[0].ondragend();
cards[2].ondrop(ev(10));
check('a drop after the drag has ended does nothing', moves.length === 0);

const plain = draw(null).filter(isCard);
check('with no onMove -- a search -- no grips, and nothing to drag',
  plain.every((c) => !c.querySelector('.grip') && !c.draggable));

finish();
