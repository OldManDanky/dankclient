// Numpad walking, with keys pressed the way a browser reports them.
'use strict';

const { El, page, load, check, same, finish } = require('./stage');

const saved = {};
let p;
const sent = [];
function open() {
  p = page({ cmd: 'input', 'numpad-mode': 'select', 'numpad-grid': 'div', 'numpad-reset': 'button' }, saved);
  global.sendCommand = (t) => sent.push(t);
  load('numpad.js');
}
const box = (value, s, t) => { p.els.cmd.value = value; p.els.cmd.selectionStart = s; p.els.cmd.selectionEnd = t; };
function key(code, over = {}) {
  const e = { code, target: p.els.cmd, repeat: false, ctrlKey: false, altKey: false, metaKey: false,
    prevented: false, preventDefault() { this.prevented = true; }, ...over };
  sent.length = 0;
  window.numpadKey(e);
  return { sent: [...sent], prevented: e.prevented };
}
const mode = (m) => { p.els['numpad-mode'].value = m; p.els['numpad-mode'].onchange(); };

open();
check('off by default: 8 is just an 8', same(key('Numpad8'), { sent: [], prevented: false }));
mode('empty');
box('', 0, 0);
check('empty box: 8 walks north', same(key('Numpad8'), { sent: ['n'], prevented: true }));
check('5 looks, then searches', same(key('Numpad5').sent, ['look', 'search']));
check('7 is north-west, + up, - down',
  same([key('Numpad7').sent, key('NumpadAdd').sent, key('NumpadSubtract').sent], [['nw'], ['u'], ['d']]));
box('kill orc ', 9, 9);
check('mid-sentence it types the digit', same(key('Numpad2'), { sent: [], prevented: false }));
box('kill orc', 0, 8);
check('a fully selected box counts as empty', same(key('Numpad2').sent, ['s']));
box('', 0, 0);
check('held down: swallowed, not sent again', same(key('Numpad8', { repeat: true }), { sent: [], prevented: true }));
check('an unset key types its own character', same(key('NumpadDivide'), { sent: [], prevented: false }));
check('Ctrl with it is left alone', same(key('Numpad8', { ctrlKey: true }), { sent: [], prevented: false }));
const field = new El('input');
field.closest = (sel) => (sel.includes('input') ? field : null);
check('a trigger being written keeps its keys', same(key('Numpad8', { target: field }), { sent: [], prevented: false }));
const xt = new El('textarea');
xt.closest = (sel) => (sel.includes('#term') || sel.includes('textarea') ? xt : null);
check("the terminal's own hidden field does not", same(key('Numpad8', { target: xt }).sent, ['n']));
mode('always');
box('kill orc ', 9, 9);
check('always: walks even with text in the box', same(key('Numpad6').sent, ['e']));
const cells = p.els['numpad-grid'].children;
check('the grid has every key, laid out as a numpad',
  same(cells.map((c) => c.children[0].textContent), ['Num', '/', '*', '-', '7', '8', '9', '+', '4', '5', '6', '1', '2', '3', 'Enter', '0', '.']));
const zero = cells.find((c) => c.children[0].textContent === '0').children[1];
zero.value = 'enter portal';
zero.oninput();
check('a key set in the grid does what it says', same(key('Numpad0').sent, ['enter portal']));
check('and is saved', JSON.parse(saved['numpad:map'])['0'] === 'enter portal');
p.els['numpad-reset'].onclick();
check('Back to the defaults: 0 types a 0 again', same(key('Numpad0'), { sent: [], prevented: false }));
open();
box('kill orc ', 9, 9);
check('a reload keeps the mode', same(key('Numpad8').sent, ['n']) && p.els['numpad-mode'].value === 'always');

finish();
