/* Dings: a sound when a tell or a channel line arrives, for the channels and
   people chosen in the messages window (right-click a line).

   Made here with the browser's own audio rather than shipped as sound files:
   a rising two-note chime for a tell, a single softer note for a channel, so
   the two can be told apart without looking.  At most one ding every 1.2
   seconds, so a busy channel is a ding and not a buzzer.

   Browsers will not play anything before somebody has clicked or typed on
   the page, so the audio is woken by the first keypress or click -- which,
   in a MUD client, is logging in. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;
  const GAP = 1.2;                       // seconds; the least between dings
  //: A tell, a channel line, and 3K's own bell -- what `wake` sends.
  const NOTES = { tell: [880, 1318.5], channel: [659.3], bell: [1046.5, 1318.5, 1568] };

  let audio = null;
  let last = -Infinity;

  function volume() {
    const v = parseInt(store.get('sound:volume', '60'), 10);
    return Number.isNaN(v) ? 60 : Math.max(0, Math.min(100, v));
  }

  function backgroundOnly() {
    return store.get('sound:background', '') === '1';
  }

  /* 3K's bell is on unless switched off, where the dings are off until
     chosen: a bell is somebody deliberately waking you, and every terminal
     there has ever been rings it. */
  function bellOn() {
    return store.get('sound:bell', '1') === '1';
  }

  function context() {
    if (!audio) {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return null;
      audio = new Audio();
    }
    if (audio.state === 'suspended' && audio.resume) audio.resume();
    return audio;
  }

  const wake = () => {
    context();
    removeEventListener('pointerdown', wake, true);
    removeEventListener('keydown', wake, true);
  };
  addEventListener('pointerdown', wake, true);
  addEventListener('keydown', wake, true);

  /* Play one.  `force` is for the test buttons and for turning a ding on:
     somebody asked to hear it, so neither the gap nor the background-only
     setting applies. */
  window.ding = function (kind, force) {
    const loud = volume() / 100;
    if (!loud) return false;
    if (!force && kind === 'bell' && !bellOn()) return false;
    if (!force && backgroundOnly() && !document.hidden
        && (!document.hasFocus || document.hasFocus())) return false;
    const c = context();
    if (!c) return false;
    const now = c.currentTime;
    if (!force && now - last < GAP) return false;
    last = now;
    (NOTES[kind] || NOTES.channel).forEach((freq, i) => {
      const at = now + i * 0.12;
      const tone = c.createOscillator();
      const level = c.createGain();
      tone.type = 'sine';
      tone.frequency.value = freq;
      level.gain.setValueAtTime(0.0001, at);
      level.gain.exponentialRampToValueAtTime(0.25 * loud, at + 0.01);
      level.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
      tone.connect(level);
      level.connect(c.destination);
      tone.start(at);
      tone.stop(at + 0.4);
    });
    return true;
  };

  // --- Options -> Panels -> Sounds -------------------------------------------

  if ($('sound-volume')) {
    $('sound-volume').value = String(volume());
    $('sound-volume').oninput = () => store.set('sound:volume', $('sound-volume').value);
  }
  if ($('sound-background')) {
    $('sound-background').checked = backgroundOnly();
    $('sound-background').onchange = () =>
      store.set('sound:background', $('sound-background').checked ? '1' : '');
  }
  if ($('sound-bell')) {
    $('sound-bell').checked = bellOn();
    $('sound-bell').onchange = () =>
      store.set('sound:bell', $('sound-bell').checked ? '1' : '');
  }
  if ($('sound-test-bell')) $('sound-test-bell').onclick = () => window.ding('bell', true);
  if ($('sound-test-tell')) $('sound-test-tell').onclick = () => window.ding('tell', true);
  if ($('sound-test-channel')) {
    $('sound-test-channel').onclick = () => window.ding('channel', true);
  }
})();
