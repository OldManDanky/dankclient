/* Sounds: a ding when a tell or a channel line arrives, for the channels and
   people chosen in the messages window (right-click a line) -- and a sound
   when a bot ends by itself, when the deadman trips, and when the MUD drops
   you.  Each can be the built-in one, nothing, or a file of your own
   (Options -> Sounds).

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
  //: A tell, a channel line, and 3K's own bell -- what `wake` sends.  Then
  //: the client's own: a bot done (falling), idle (two low), dropped (low, lower).
  const NOTES = {
    tell: [880, 1318.5], channel: [659.3], bell: [1046.5, 1318.5, 1568],
    bot: [1174.7, 880, 659.3], idle: [440, 440], disconnect: [392, 261.6],
  };

  /* What each event plays -- built in, nothing, or your own file -- as the
     server keeps it with the map (see sounds.py).  Until it says, built in. */
  let chosen = {};

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
    const mine = chosen[kind] || {};
    if (mine.choice === 'none') return false;
    if (!force && kind === 'bell' && !bellOn()) return false;
    if (!force && backgroundOnly() && !document.hidden
        && (!document.hasFocus || document.hasFocus())) return false;
    const c = context();
    if (!c) return false;
    const now = c.currentTime;
    if (!force && now - last < GAP) return false;
    last = now;
    if (mine.choice === 'file' && window.Audio) {
      // Yours, from the client; the stamp gets past the page's cache when
      // the file is replaced.
      const clip = new window.Audio(`/sounds/${kind}?v=${mine.stamp || 0}`);
      clip.volume = loud;
      const played = clip.play();
      if (played && played.catch) played.catch(() => {});
      return true;
    }
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

  // --- Options -> Sounds -----------------------------------------------------

  const CHOICE_LABELS = { builtin: 'built-in', none: 'no sound', file: 'your file' };
  //: Biggest upload; the server says the same (sounds.MOST).
  const MOST = 2 << 20;

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'sound' }, msg)));
    }
  }

  function upload(slot, file) {
    if (!file) return;
    if (file.size > MOST) {
      say(`${file.name} is ${(file.size / 1048576).toFixed(1)} MB; the most is 2 MB`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      send({ op: 'upload', slot, name: file.name, data: text.slice(text.indexOf(',') + 1) });
      say(`uploading ${file.name}\u2026`);
    };
    reader.readAsDataURL(file);
  }

  function say(text) {
    if ($('sound-error')) $('sound-error').textContent = text || '';
  }

  /* One row per event: what it plays, your file if you gave one, Upload,
     and a button to hear it. */
  function drawRows(slots) {
    const box = $('sound-rows');
    if (!box) return;
    box.replaceChildren();
    for (const s of slots) {
      const row = document.createElement('div');
      row.className = 'sound-row';
      const label = document.createElement('span');
      label.className = 'sound-label';
      label.textContent = s.label;

      const pick = document.createElement('select');
      for (const c of ['builtin', 'none', 'file']) {
        if (c === 'file' && !s.name) continue;
        const o = document.createElement('option');
        o.value = c;
        o.textContent = c === 'file' ? `your file: ${s.name}` : CHOICE_LABELS[c];
        pick.append(o);
      }
      pick.value = s.choice;
      pick.setAttribute('aria-label', `${s.label}: which sound`);
      pick.onchange = () => send({ op: 'choose', slot: s.slot, choice: pick.value });

      const file = document.createElement('input');
      file.type = 'file';
      file.accept = 'audio/*,.mp3,.wav,.ogg,.m4a';
      file.hidden = true;
      file.onchange = () => upload(s.slot, file.files && file.files[0]);
      const up = document.createElement('button');
      up.type = 'button';
      up.className = 'sound-up';
      up.textContent = s.name ? 'Replace\u2026' : 'Upload\u2026';
      up.onclick = () => file.click();

      const hear = document.createElement('button');
      hear.type = 'button';
      hear.textContent = '\u25B6';
      hear.title = 'Play it';
      hear.setAttribute('aria-label', `Play the sound for: ${s.label}`);
      hear.onclick = () => window.ding(s.slot, true);

      // There on every row, empty and unseen where there is no file, so the
      // columns line up.
      const drop = document.createElement('button');
      drop.type = 'button';
      drop.className = 'sound-drop';
      if (s.name) {
        drop.textContent = '\u00D7';
        drop.title = `Remove ${s.name} and go back to the built-in sound`;
        drop.onclick = () => send({ op: 'remove', slot: s.slot });
      } else {
        drop.tabIndex = -1;
        drop.setAttribute('aria-hidden', 'true');
      }
      row.append(label, pick, up, file, hear, drop);
      box.append(row);
    }
  }

  //: From the server: on connecting, and after every change made here.
  window.setSounds = function (slots, error) {
    chosen = {};
    for (const s of slots || []) chosen[s.slot] = s;
    drawRows(slots || []);
    say(error || '');
  };

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
  // Before the server has said anything, the events with their built-in sounds.
  drawRows([
    ['tell', 'A tell to you'], ['channel', 'A channel line you chose to ding'],
    ['bell', "3K's bell (somebody used wake)"], ['bot', 'A bot ends by itself'],
    ['idle', 'You have been idle (the deadman trips)'], ['disconnect', 'The MUD drops you'],
  ].map(([slot, label]) => ({ slot, label, choice: 'builtin', name: '' })));
})();
