// The messages window: colours, "mine", and dings, run for real.
'use strict';

const { El, page, messagesWindow, load, check, same, finish } = require('./stage');

const saved = {};
const heard = [];
let root;

function open() {
  root = messagesWindow();
  const p = page({}, saved);
  document.getElementById = (id) => (id === 'msgmon' ? root : null);
  global.ding = (kind, force) => { heard.push(kind + (force ? '(test)' : '')); return true; };
  load('chat.js');
  return p;
}

const body = () => root.querySelector('.cm-body');
const filters = () => root.querySelector('.cm-filters');
const rows = () => body().querySelectorAll('.cm-msg');
const texts = () => body().querySelectorAll('.cm-txt').map((t) => t.textContent);
const colour = (i) => rows()[i].querySelector('.cm-txt').style.color || '(none)';
const menu = () => document.body.querySelector('.cm-menu');
const click = (x, y) => ({ preventDefault() { this.prevented = true; }, stopPropagation() {}, clientX: x, clientY: y });
const hear = (fn) => { heard.length = 0; fn(); return [...heard]; };
const clan = (who, text) => pushMessage('chat', { who, channel: 'Clan', command: 'ctell', message: `[Clan] ${who} : ${text}` });

// --- colours --------------------------------------------------------------------
let p = open();
clan('Friend', 'moo');
clan('Other', 'hi');
pushMessage('chat', { who: 'Friend', channel: 'Public', command: 'pub', message: 'Friend shouts: hey' });
pushMessage('tell', { who: 'Buddy', message: 'psst', from_me: false });

let e = click(990, 790);
rows()[0].oncontextmenu(e);
check("right-click opens the menu, and the browser's own is suppressed", !!menu() && e.prevented);
check('the menu stays on screen near a corner',
  menu().style.left === '796px' && menu().style.top === '676px', [menu().style.left, menu().style.top]);
const heads = menu().querySelectorAll('h6').map((h) => h.textContent);
check('it offers the channel, the person, and dings', same(heads, ['The Clan channel', 'Everything from Friend', 'Ding']), heads);
menu().querySelectorAll('.cm-swatches')[0].querySelectorAll('.cm-swatch')[3].onclick();
check('picking closes the menu', !menu());
check('every Clan line takes the colour, nothing else',
  same([0, 1, 2, 3].map(colour), ['#7ee787', '#7ee787', '(none)', '(none)']), [0, 1, 2, 3].map(colour));
const clanTag = filters().querySelectorAll('button').find((b) => b.textContent === 'Clan');
check('the Clan tag carries it', (clanTag.style.boxShadow || '').includes('#7ee787'));
rows()[0].oncontextmenu(click(10, 10));
menu().querySelectorAll('.cm-swatches')[1].querySelectorAll('.cm-swatch')[7].onclick();
check("a person's colour beats their channel's",
  same([0, 1, 2].map(colour), ['#ff9bce', '#7ee787', '#ff9bce']), [0, 1, 2].map(colour));
rows()[3].oncontextmenu(click(10, 10));
for (const f of [...(p.listeners.keydown || [])]) f({ key: 'Escape', preventDefault() {}, stopPropagation() {} });
check('Escape closes it without choosing', !menu());
rows()[0].oncontextmenu(click(10, 10));
menu().querySelectorAll('.cm-swatches')[1].querySelectorAll('.cm-swatch')[7].onclick();
check('picking a colour again takes it off', colour(0) === '#7ee787', colour(0));
p = open();
clan('Other', 'back');
check('colours survive a reload', colour(0) === '#7ee787', colour(0));

// --- mine -------------------------------------------------------------------------
for (const k of Object.keys(saved)) delete saved[k];
p = open();
const say = () => {
  clan('Player', 'back soon');
  clan('Friend', 'ok');
  pushMessage('chat', { who: 'Other', channel: 'Public', command: 'pub', message: 'Other shouts: hey' });
  pushMessage('chat', { who: 'PLAYER', channel: 'Public', command: 'pub', message: 'Player shouts: hi all' });
  pushMessage('tell', { who: 'Buddy', message: 'psst', from_me: false });
  pushMessage('tell', { who: 'Buddy', message: 'on my way', from_me: true });
};
say();
const mine = () => filters().querySelectorAll('button').find((b) => b.textContent === 'mine');
check('a tell you sent counts as yours before your name is known', !!mine());
setMe('player');
check('the mine tag sits last', filters().children[filters().children.length - 1] === mine());
mine().onclick({ stopPropagation() {} });
check('hides your channel lines, whatever the case, and your sent tell',
  same(texts(), ['[Clan] Friend : ok', 'Other shouts: hey', 'psst']), texts());
check('the count says what is hidden', root.querySelector('.cm-count').textContent === '3 of 6');
p = open(); say(); setMe('Player');
check('a reload keeps them hidden', texts().length === 3);
mine().onclick({ stopPropagation() {} });
check('clicking again brings them back', texts().length === 6);
for (const k of Object.keys(saved)) delete saved[k];
p = open(); setMe('player');
clan('Player', 'hi');
check('one channel: no lone tag, but mine is offered',
  same(filters().querySelectorAll('button').map((b) => b.textContent), ['mine']));

// --- dings --------------------------------------------------------------------------
for (const k of Object.keys(saved)) delete saved[k];
p = open(); setMe('Player');
check('nothing dings until chosen', hear(() => clan('Friend', 'hi')).length === 0);
rows()[0].oncontextmenu(click(10, 10));
const choices = menu().querySelectorAll('.cm-ding').map((b) => b.textContent);
check('the Ding row offers the channel and the person', same(choices, ['every Clan line', 'anything from Friend']), choices);
check('turning one on plays it once', same(hear(() => menu().querySelectorAll('.cm-ding')[0].onclick()), ['channel(test)']));
check('then another Clan line dings', same(hear(() => clan('Other', 'yo')), ['channel']));
check('your own line does not', hear(() => clan('Player', 'me')).length === 0);
pushMessage('chat', { who: 'Buddy', channel: 'Public', command: 'pub', message: 'Buddy shouts: hey' });
const tagNow = filters().querySelectorAll('button').find((b) => b.textContent === 'Clan');
check('the Clan tag shows that it dings', tagNow.className.split(' ').includes('dings'), tagNow.className);
tagNow.onclick({ stopPropagation() {} });
check('a hidden channel does not ding', hear(() => clan('Other', 'quiet')).length === 0);
const buddy = rows().find((r) => r.querySelector('.cm-txt').textContent.includes('Buddy'));
buddy.oncontextmenu(click(10, 10));
hear(() => menu().querySelectorAll('.cm-ding')[1].onclick());
check("a person's ding covers their tells, with the tell sound",
  same(hear(() => pushMessage('tell', { who: 'Buddy', message: 'psst', from_me: false })), ['tell']));
check('a tell you send them does not', hear(() => pushMessage('tell', { who: 'Buddy', message: 'ok', from_me: true })).length === 0);
p = open(); setMe('Player');
check('dings survive a reload', same(hear(() => pushMessage('tell', { who: 'buddy', message: 'again', from_me: false })), ['tell']));

void El;
finish();
