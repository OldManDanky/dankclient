// Your commands: saved across a reload, searched, and picked into the box.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const saved = {};
let p;
function open() {
  p = page({ cmd: 'input', hist: 'div', 'hist-find': 'input', 'hist-list': 'div',
    'hist-open': 'button' }, saved);
  p.els.hist.hidden = true;
  load('history.js');
}
open();

const H = () => window.cmdHistory;
const rows = () => p.els['hist-list'].children.filter((c) => c.className.startsWith('hist-row'));
const texts = () => rows().map((r) => r.textContent);
const key = (k) => {
  const e = { key: k, prevented: false, preventDefault() { this.prevented = true; },
    stopPropagation() {} };
  p.els['hist-find'].onkeydown(e);
  return e;
};
const search = (q) => { p.els['hist-find'].value = q; p.els['hist-find'].oninput(); };

H().add('hunter2', false);
check('typed before MIP is live: there for ↑, never saved',
  same(H().list(), ['hunter2']) && !('cmd:history' in saved), saved);
for (const c of ['kill rat', 'get all', 'kill rat', 'tell buddy hi', 'tell buddy hi']) H().add(c, true);
check('a command sent twice running is one entry',
  same(H().list(), ['hunter2', 'kill rat', 'get all', 'kill rat', 'tell buddy hi']), H().list());
check('what is saved is only what came once MIP was live',
  same(JSON.parse(saved['cmd:history']), ['kill rat', 'get all', 'kill rat', 'tell buddy hi']));

p.els['hist-open'].onclick();
check('History opens the list: newest first, each command once, the search box ready',
  !p.els.hist.hidden && same(texts(), ['tell buddy hi', 'kill rat', 'get all', 'hunter2'])
  && p.els['hist-find'].focused, texts());
search('RAT');
check('a search narrows it, whatever the case', same(texts(), ['kill rat']), texts());
search('zzz');
check('and says so when nothing matches',
  rows().length === 0 && p.els['hist-list'].children[0].textContent.includes('zzz'));
search('');
rows()[2].onclick();
check('clicking one puts it in the command box and closes the list',
  p.els.cmd.value === 'get all' && p.els.hist.hidden && p.els.cmd.focused, p.els.cmd.value);

H().open();
key('ArrowDown');
check('↓ moves down the list', rows()[1].className === 'hist-row on');
const enter = key('Enter');
check('Enter puts that one in the box, without submitting the command box',
  p.els.cmd.value === 'kill rat' && enter.prevented && p.els.hist.hidden, p.els.cmd.value);
H().open();
key('ArrowUp');
check('↑ stops at the top', rows()[0].className === 'hist-row on');
key('Escape');
check('Esc closes it', p.els.hist.hidden);
H().open();
p.listeners.mousedown.forEach((f) => f({ target: p.els.cmd }));
check('clicking anywhere else closes it', p.els.hist.hidden);

open();
check('a reload keeps what was saved, and not what came before MIP',
  same(window.cmdHistory.list(), ['kill rat', 'get all', 'kill rat', 'tell buddy hi']));
for (let i = 0; i < 600; i++) window.cmdHistory.add(`say ${i}`, true);
check('the last 500 are kept',
  window.cmdHistory.list().length === 500 && JSON.parse(saved['cmd:history']).length === 500
  && window.cmdHistory.list()[499] === 'say 599');

finish();
