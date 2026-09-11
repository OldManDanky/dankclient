// Dings' sound, against a fake audio device whose clock is ours.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const played = [];
let peak = 0;
let audio = null;
class FakeAudio {
  constructor() { this.currentTime = 100; this.state = 'running'; this.destination = {}; audio = this; }
  createOscillator() {
    const o = { type: '', frequency: { value: 0 }, connect() {}, stop() {},
      start: (t) => played.push({ f: o.frequency.value, at: t }) };
    return o;
  }
  createGain() {
    return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime: (v) => { peak = Math.max(peak, v); } },
      connect() {} };
  }
}

const saved = {};
const p = page({ 'sound-volume': 'input', 'sound-background': 'input', 'sound-bell': 'input',
  'sound-rows': 'div', 'sound-error': 'p' }, saved);
global.AudioContext = FakeAudio;
let focused = true;
document.hasFocus = () => focused;
load('sound.js');
// Each event's row: its label, the choice, Upload, a file box, and play.
const row = (slot) => p.els['sound-rows'].children.find((r) => r.children[0].textContent
  === { tell: 'A tell to you', bell: "3K's bell (somebody used wake)", bot: 'A bot ends by itself' }[slot]);
const play = (slot) => row(slot).children.find((b) => b.title === 'Play it').onclick();

const fresh = () => { played.length = 0; peak = 0; };
const notes = () => played.map((n) => n.f);

fresh(); ding('tell');
check('a tell chimes twice, rising', same(notes(), [880, 1318.5]), notes());
fresh();
check('a second ding inside 1.2s is skipped', ding('channel') === false && played.length === 0);
audio.currentTime += 1.3;
fresh();
check('after the gap a channel line gets one note', ding('channel') === true && same(notes(), [659.3]), notes());
fresh();
check('a test always plays, gap or not', ding('channel', true) === true && played.length === 1);
saved['sound:volume'] = '0';
fresh();
check('volume 0 is silent', ding('tell', true) === false && played.length === 0);
saved['sound:volume'] = '60';
saved['sound:background'] = '1';
audio.currentTime += 5;
fresh();
check('background-only: quiet while the window has focus', ding('tell') === false);
focused = false;
fresh();
check('and plays when it does not', ding('tell') === true);
check('the slider starts at the saved volume', p.els['sound-volume'].value === '60');
p.els['sound-volume'].value = '40';
p.els['sound-volume'].oninput();
check('moving it saves it', saved['sound:volume'] === '40');
p.els['sound-background'].checked = false;
p.els['sound-background'].onchange();
check('the background box saves too', saved['sound:background'] === '');
fresh();
play('tell');
check("a tell's play button plays the tell", same(notes(), [880, 1318.5]));
check('the loudest it gets follows the volume', peak > 0 && peak <= 0.25 * 0.4 + 1e-9, peak);

// 3K's bell: what `wake` sends.
check('the bell box starts ticked', p.els['sound-bell'].checked === true);
audio.currentTime += 5;
fresh();
check("3K's bell rings, three notes, without being asked for",
  ding('bell') === true && same(notes(), [1046.5, 1318.5, 1568]), notes());
p.els['sound-bell'].checked = false;
p.els['sound-bell'].onchange();
audio.currentTime += 5;
fresh();
check('switched off, the bell is silent', ding('bell') === false && played.length === 0);
fresh();
play('bell');
check('its play button still plays it', played.length === 3);
check('and the choice is saved', saved['sound:bell'] === '');


// --- the new events, and your own files -----------------------------------------
check('every event has a row before the server says anything', p.els['sound-rows'].children.length === 6);
audio.currentTime += 5;
fresh();
check('a bot ending has a sound of its own', ding('bot') === true && same(notes(), [1174.7, 880, 659.3]), notes());

const sent = [];
global.ws = { readyState: 1, send: (m) => sent.push(JSON.parse(m)) };
const clips = [];
global.Audio = class { constructor(src) { this.src = src; clips.push(this); } play() { this.played = true; return Promise.resolve(); } };
const slots = (over) => ['tell', 'channel', 'bell', 'bot', 'idle', 'disconnect'].map((slot) => Object.assign(
  { slot, label: { tell: 'A tell to you', bell: "3K's bell (somebody used wake)", bot: 'A bot ends by itself' }[slot] || slot,
    choice: 'builtin', name: '', stamp: 0 }, over[slot] || {}));
setSounds(slots({ bot: { choice: 'file', name: 'horn.mp3', stamp: 42 }, tell: { choice: 'none' } }));
audio.currentTime += 5;
fresh();
check('your own file plays from the client, past the cache, at the volume',
  ding('bot') === true && played.length === 0 && clips.length === 1
  && clips[0].src === '/sounds/bot?v=42' && clips[0].played && Math.abs(clips[0].volume - 0.4) < 1e-9,
  clips.map((c) => c.src));
audio.currentTime += 5;
check("'no sound' is silent, even from its play button", ding('tell') === false && ding('tell', true) === false);
const pick = row('bot').children.find((c) => c.tagName === 'select');
check('the row offers your file by name', pick.children.map((o) => o.textContent).includes('your file: horn.mp3')
  && pick.value === 'file');
pick.value = 'builtin';
pick.onchange();
check('choosing tells the server', same(sent[sent.length - 1], { t: 'sound', op: 'choose', slot: 'bot', choice: 'builtin' }));
row('bot').children.find((b) => b.title && b.title.startsWith('Remove')).onclick();
check('× removes your file', same(sent[sent.length - 1], { t: 'sound', op: 'remove', slot: 'bot' }));
check('a row without a file has no × and says Upload',
  !row('tell').children.some((b) => b.title && b.title.startsWith('Remove'))
  && row('tell').children.some((b) => b.textContent === 'Upload\u2026'));

global.FileReader = class { readAsDataURL(f) { this.result = 'data:audio/mpeg;base64,' + f.b64; this.onload(); } };
const box = row('tell').children.find((c) => c.type === 'file');
box.files = [{ name: 'moo.mp3', size: 1000, b64: 'AAAA' }];
box.onchange();
check('uploading sends the file to the server, without the data: prefix',
  same(sent[sent.length - 1], { t: 'sound', op: 'upload', slot: 'tell', name: 'moo.mp3', data: 'AAAA' }), sent[sent.length - 1]);
const before = sent.length;
box.files = [{ name: 'long.wav', size: 3 << 20, b64: '' }];
box.onchange();
check('a file over 2 MB is refused here, with a reason', sent.length === before
  && p.els['sound-error'].textContent.includes('the most is 2 MB'), p.els['sound-error'].textContent);
setSounds(slots({}), 'that file is empty');
check("the server's reason is shown", p.els['sound-error'].textContent === 'that file is empty');

finish();
