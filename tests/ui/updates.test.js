// The Updates panel: what may be ticked, and arming the one-way button.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const p = page({
  'up-list': 'div', 'up-pull': 'button', 'up-check': 'button',
  'up-fresh': 'button', 'up-note': 'p',
});
const sent = [];
global.ws = { readyState: 1, send: (s) => sent.push(JSON.parse(s)) };

load('updates.js');

const state = (items, changed) => ({ op: 'state', items, changed });
const boxes = () => p.els['up-list'].querySelectorAll('input[type=checkbox]');
const byKey = (k) => boxes().find((b) => b.dataset.key === k);

handleUpdate(state({
  map: { there: true, changed: false, size: 26214400 },
  speedruns: { there: true, changed: true, size: 4096 },
  bots: { there: false, changed: false },
}, ['speedruns']));

check('an up-to-date thing can still be ticked',
      byKey('map') && byKey('map').disabled === false && byKey('map').checked === false);
check('a changed one is ticked to start with',
      byKey('speedruns').checked === true);
check('one the repository does not have cannot be ticked',
      byKey('bots').disabled === true);
check('both buttons are live while something is ticked',
      p.els['up-pull'].disabled === false && p.els['up-fresh'].disabled === false);

// Untick everything: neither button has anything to act on.
byKey('speedruns').checked = false;
byKey('speedruns').onchange();
check('and dead when nothing is',
      p.els['up-pull'].disabled === true && p.els['up-fresh'].disabled === true);

// Fresh copy takes two presses, and says what it costs on the first.
byKey('map').checked = true;
byKey('map').onchange();
sent.length = 0;
p.els['up-fresh'].onclick();
check('the first press sends nothing', sent.length === 0, sent);
check('it arms instead, and says so',
      p.els['up-fresh'].textContent === 'Drop and take — click again');
check('and says what it costs',
      /drops your copy/.test(p.els['up-note'].textContent)
      && /session log are kept/.test(p.els['up-note'].textContent),
      p.els['up-note'].textContent);

p.els['up-fresh'].onclick();
check('the second press asks for a fresh copy of what is ticked',
      sent.length === 1 && sent[0].fresh === true && same(sent[0].want, ['map']),
      sent);
check('and the button is not left armed',
      p.els['up-fresh'].textContent === 'Fresh copy');

// An ordinary take is never a drop.
handleUpdate(state({ map: { there: true, changed: true, size: 10 } }, ['map']));
sent.length = 0;
p.els['up-pull'].onclick();
check('Take updates never asks for a drop',
      sent.length === 1 && !sent[0].fresh, sent);

// Arming, then ticking something else, disarms: the warning named the old set.
handleUpdate(state({
  map: { there: true, changed: true, size: 10 },
  speedruns: { there: true, changed: false, size: 10 },
}, ['map']));
p.els['up-fresh'].onclick();
check('armed', p.els['up-fresh'].dataset.armed === '1');
byKey('map').checked = false;
byKey('map').onchange();
check('unticking the last one disarms it',
      p.els['up-fresh'].dataset.armed !== '1'
      && p.els['up-fresh'].textContent === 'Fresh copy');

finish();
