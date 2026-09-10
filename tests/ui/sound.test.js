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
  'sound-test-bell': 'button', 'sound-test-tell': 'button', 'sound-test-channel': 'button' }, saved);
global.AudioContext = FakeAudio;
let focused = true;
document.hasFocus = () => focused;
load('sound.js');

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
p.els['sound-test-tell'].onclick();
check('Test a tell plays the tell', same(notes(), [880, 1318.5]));
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
p.els['sound-test-bell'].onclick();
check('Test the bell still plays it', played.length === 3);
check('and the choice is saved', saved['sound:bell'] === '');

finish();
