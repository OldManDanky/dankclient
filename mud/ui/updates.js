/* Map and bot updates, from the repository this map came from.

   https://github.com/jmitchell33/3kdb is a TinTin++ setup for 3K and it keeps
   growing. Nobody should have to notice by hand, and nobody should have to
   trust a button that might cost them the map they have -- so taking an update
   only ever adds, and this screen says what it is about to add before it does.

   Three things are watched, and all three are data: the map is parsed into
   SQLite and the bot files are read with a regex. Nothing pulled here is
   executed, which is the reason this is a button at all. */

(function () {
  const $ = (id) => document.getElementById(id);

  //: what the server calls each of them, and what to call them on screen
  const NAMES = {
    map: ['The map', 'Rooms, exits and areas — 3k_shared.map'],
    speedruns: ['Named destinations', 'What /go walks to — speedruns.tin'],
    bots: ['Bot library', 'Routes: where the monsters are, and in what order'],
    gags: ['Gag library', 'Lines 3kdb players hide — every group off until you switch it on'],
  };

  let state = null;           // the last answer from GitHub, or null
  let working = false;

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'update' }, msg)));
    }
  }

  function size(n) {
    if (!n) return '';
    return n > 1048576 ? `${(n / 1048576).toFixed(1)} MB`
         : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} bytes`;
  }

  /* Which ones are ticked. Everything changed, unless you say otherwise. */
  function wanted() {
    return [...$('up-list').querySelectorAll('input[type=checkbox]')]
      .filter((box) => box.checked).map((box) => box.dataset.key);
  }

  function row(key, item) {
    const el = document.createElement('div');
    el.className = 'char';

    const box = document.createElement('div');
    box.className = 'who';
    const nm = document.createElement('div');
    nm.className = 'nm';

    const tick = document.createElement('input');
    tick.type = 'checkbox';
    tick.dataset.key = key;
    tick.checked = !!item.changed;
    // Anything 3kdb actually has can be ticked, changed or not: a fresh copy
    // of something already up to date is the whole point of Fresh copy, and
    // re-taking one that has not changed was not possible at all before.
    tick.disabled = !item.there;
    tick.onchange = gate;
    nm.append(tick, document.createTextNode(' ' + (NAMES[key] || [key])[0]));

    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = [
      (NAMES[key] || [key, ''])[1],
      size(item.size),
      !item.there ? 'not in the repository'
        : item.new ? 'never taken'
        : item.changed ? 'changed since you took it'
        : 'up to date',
    ].filter(Boolean).join('  ·  ');
    box.append(nm, sub);
    el.append(box);
    return el;
  }

  /* The buttons, against what is ticked right now.  Separate from render()
     because a tick must not redraw the box being ticked. */
  function gate() {
    const n = wanted().length;
    $('up-pull').disabled = working || !n;
    $('up-fresh').disabled = working || !n;
    $('up-check').disabled = working;
    if (!n) disarm();
  }

  function disarm() {
    const b = $('up-fresh');
    b.dataset.armed = '';
    b.textContent = 'Fresh copy';
  }

  function render() {
    const list = $('up-list');
    list.replaceChildren();
    if (!state || !state.items) {
      gate();
      return;
    }
    for (const key of Object.keys(NAMES)) {
      if (state.items[key]) list.append(row(key, state.items[key]));
    }
    gate();
    if (window.options) window.options.count('updates', (state.changed || []).length);
  }

  function say(text, bad) {
    const note = $('up-note');
    note.textContent = text;
    note.style.color = bad ? 'var(--bad)' : '';
  }

  $('up-check').onclick = () => {
    say('asking GitHub...');
    send({ op: 'check' });
  };

  $('up-pull').onclick = () => {
    const want = wanted();
    if (!want.length) return;
    disarm();
    working = true;
    render();
    say('fetching — the map alone is 25MB, so give it a moment...');
    send({ op: 'pull', want });
  };

  /* Dropping what you have is worth two presses: the same arming the other
     one-way buttons here use, rather than a dialog. */
  $('up-fresh').onclick = () => {
    const want = wanted();
    if (!want.length) return;
    const b = $('up-fresh');
    if (b.dataset.armed !== '1') {
      b.dataset.armed = '1';
      b.textContent = 'Drop and take — click again';
      const names = want.map((k) => (NAMES[k] || [k])[0].toLowerCase());
      say(`this drops your copy of ${names.join(', ')} and takes 3kdb's `
          + 'instead. Room names you set, visit counts and exits you walked '
          + 'go with it. Your own routes and your session log are kept.');
      return;
    }
    disarm();
    working = true;
    render();
    say('fetching — the map alone is 25MB, so give it a moment...');
    send({ op: 'pull', want, fresh: true });
  };

  /* What came back. */
  function did(got) {
    const done = got.did || {};
    const said = [];
    if (done.map) {
      said.push(`map: ${done.map.rooms} rooms, ${done.map.edges} exits`
                + (done.map.scrubbed
                   ? `, ${done.map.scrubbed} exits cleaned of TinTin++` : '')
                + (done.map.refiled !== undefined
                   ? `, ${done.map.refiled} logged lines still filed by room`
                     + (done.map.unfiled
                        ? ` (${done.map.unfiled} were in rooms 3kdb does not have)`
                        : '')
                   : ''));
    }
    if (done.speedruns) said.push(`${done.speedruns.added} destinations`);
    if (done.bots) {
      said.push(`${done.bots.added} routes added`
                + (done.bots.dropped ? `, ${done.bots.dropped} of 3kdb's replaced` : '')
                + (done.bots.kept ? `, ${done.bots.kept} of yours left alone` : ''));
    }
    if (done.gags) {
      said.push(`${done.gags.gags} gags in ${done.gags.groups} groups — switch them on `
                + 'under Options → Gag library');
    }
    return said.length ? said.join('  ·  ') : 'nothing to take.';
  }

  window.handleUpdate = function (m) {
    if (m.op === 'release') {
      if (window.renderRelease) window.renderRelease(m);
      return;
    }
    if (m.op === 'working') {
      working = true;
      render();
      return;
    }
    working = false;
    if (m.error) {
      state = m.items ? m : state;
      render();
      say(m.error, true);
      return;
    }
    state = m;
    render();
    say(m.op === 'done'
        ? (m.nothing ? 'Already up to date.' : 'Taken — ' + did(m))
        : ((m.changed || []).length
            ? 'Tick what to take, then Take updates.'
            : 'Everything is up to date.'));
  };

  // Ask once there is a socket to ask down, so the tab carries a count
  // whether or not anybody has opened it.
  if (window.whenConnected) {
    window.whenConnected(() => send({ op: 'check' }));
  }
})();
