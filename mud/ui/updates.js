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
    tick.disabled = !item.changed;
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

  function render() {
    const list = $('up-list');
    list.replaceChildren();
    if (!state || !state.items) return;
    for (const key of Object.keys(NAMES)) {
      if (state.items[key]) list.append(row(key, state.items[key]));
    }
    const changed = (state.changed || []).length;
    $('up-pull').disabled = working || !changed;
    $('up-check').disabled = working;
    if (window.options) window.options.count('updates', changed);
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
    working = true;
    render();
    say('fetching — the map alone is 25MB, so give it a moment...');
    send({ op: 'pull', want });
  };

  /* What came back. */
  function did(got) {
    const done = got.did || {};
    const said = [];
    if (done.map) {
      said.push(`map: ${done.map.rooms} rooms, ${done.map.edges} exits`
                + (done.map.scrubbed
                   ? `, ${done.map.scrubbed} exits cleaned of TinTin++` : ''));
    }
    if (done.speedruns) said.push(`${done.speedruns.added} destinations`);
    if (done.bots) {
      said.push(`${done.bots.added} routes added`
                + (done.bots.kept ? `, ${done.bots.kept} of yours left alone` : ''));
    }
    return said.length ? said.join('  ·  ') : 'nothing to take.';
  }

  window.handleUpdate = function (m) {
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
