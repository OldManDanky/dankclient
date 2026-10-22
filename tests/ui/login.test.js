// The character screen: which MUD a character plays, and that it is a choice
// of the two rather than an address box nobody connects to.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const sent = [];
const p = page({
  login: 'div', 'char-list': 'div', 'char-form': 'form', 'char-form-title': 'h3',
  'char-error': 'p', 'char-add': 'button', 'char-cancel': 'button',
  'login-skip': 'button', 'login-state': 'p', 'open-login': 'button',
  'setup-who': 'p', 'c-name': 'input', 'c-world': 'select',
  'c-profession': 'select', 'c-profession-hint': 'p', 'c-extras': 'div',
  'c-password': 'input', 'c-password-hint': 'p', 'c-remember': 'input',
  'c-note': 'input',
});
global.ws = { readyState: 1, send: (m) => sent.push(JSON.parse(m)) };
global.confirm = () => true;
load('login.js');

const WORLDS = [
  { id: '3k', name: 'Three Kingdoms', host: '3k.org', port: 3000 },
  { id: '3s', name: '3Scapes', host: '3scapes.org', port: 3200 },
];
const who = (extra) => Object.assign({
  offline: false, character: null, me: '', known: [], worlds: WORLDS,
  professions: [], extras: [], asking: true, needed: true,
}, extra);

const PLAYER = { name: 'Player', host: '3k.org', port: 3000, world: '3k',
  has_password: false, note: '', profession: '', extras: [], slug: 'player' };
const OTHER = { name: 'Other', host: '3scapes.org', port: 3200, world: '3s',
  has_password: false, note: '', profession: '', extras: [], slug: 'other' };

renderWho(who({ known: [PLAYER, OTHER] }));

const sel = p.els['c-world'];
const options = () => sel.children.map((o) => [o.value, o.textContent]);

// --- the choice -------------------------------------------------------------

p.els['char-add'].onclick();
check('the form offers the two MUDs and nothing else',
  same(options(), [['3k', 'Three Kingdoms  ·  3k.org:3000'],
                   ['3s', '3Scapes  ·  3scapes.org:3200']]), options());
check('a new character starts on Three Kingdoms', sel.value === '3k', sel.value);

p.els['c-name'].value = 'Buddy';
sel.value = '3s';
p.els['char-form'].onsubmit({ preventDefault() {} });
check('saving sends 3Scapes\' own address, not one the page made up',
  same(sent.splice(0)[0].character, {
    name: 'Buddy', world: '3s', host: '3scapes.org', port: 3200,
    password: '', remember: false, note: '', profession: '', extras: [],
  }));

// --- editing one that already exists ----------------------------------------

const rows = () => p.els['char-list'].children;
const press = (row, label) => row.querySelectorAll('button')
  .find((b) => b.textContent === label).onclick();

press(rows()[1], 'Edit');
check('editing a 3Scapes character opens on 3Scapes', sel.value === '3s', sel.value);
press(rows()[0], 'Edit');
check('and a 3K one on Three Kingdoms', sel.value === '3k', sel.value);

// An entry saved before the choice existed carries the address only.
renderWho(who({ known: [Object.assign({}, OTHER, { world: undefined })] }));
press(rows()[0], 'Edit');
check('an older entry is placed by its address', sel.value === '3s', sel.value);

// --- the list says which game -----------------------------------------------

renderWho(who({ known: [PLAYER, OTHER] }));
const sub = (row) => row.querySelector('.sub').textContent;
check('each character says which MUD it plays, by name',
  sub(rows()[0]).startsWith('Three Kingdoms')
  && sub(rows()[1]).startsWith('3Scapes'),
  [sub(rows()[0]), sub(rows()[1])]);

// --- and playing one is what connects ---------------------------------------

sent.length = 0;
renderWho(who({ known: [PLAYER, Object.assign({}, OTHER, { has_password: true })] }));
press(rows()[1], 'Play');
check('playing sends the name; the server takes them to their own MUD',
  same(sent, [{ t: 'login', op: 'play', name: 'Other', password: '', remember: false }]),
  sent);

finish();
