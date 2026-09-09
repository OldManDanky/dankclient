/* Who is playing.

   A player has several characters and their aliases are not interchangeable:
   half of one character's are commands another does not have.  So the
   client has to know who it is before it loads any of them, and the honest
   moment to ask is while the MUD is asking the same question.

   The screen shows itself only before anyone has said.  Somebody who types
   their own name past it is already in, so it gets out of the way rather than
   sitting over the game -- the sidebar button brings it back. */

(function () {
  const $ = (id) => document.getElementById(id);
  let who = { character: null, known: [], asking: false, needed: false,
              offline: false };
  let editing = null;             // the character being edited, or null
  let forced = false;             // opened from the sidebar, not by the client

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'login' }, msg)));
    }
  }

  function open(on) {
    forced = !!on;
    $('login').hidden = !on;
    if (on) {
      form(null, false);
      const first = $('char-list').querySelector('button');
      (first || $('char-add')).focus();
    } else if (window.focusInput) {
      window.focusInput();
    }
  }

  $('open-login').onclick = () => open($('login').hidden);
  /* Pressing Disconnect brings this up, and so does the sidebar banner: after
     a hang-up the question "who is playing" is the same question as "how do I
     get back on", and one screen answers both. */
  window.openLogin = () => open(true);
  $('login-skip').onclick = () => {
    // Dismissed on the server, so a refresh does not put it back in the way.
    if (!who.character) send({ op: 'skip' });
    open(false);
  };
  addEventListener('keydown', (e) => {
    // Only when it is not the thing standing between you and the game.
    if (e.key === 'Escape' && !$('login').hidden && (forced || who.character)) {
      open(false);
      e.preventDefault();
    }
  });

  // --- add / edit -----------------------------------------------------------

  function form(char, show) {
    editing = char || null;
    $('char-form').hidden = !show;
    $('char-error').textContent = '';
    $('char-form-title').textContent = char ? `Edit ${char.name}` : 'Add a character';
    $('c-name').value = char ? char.name : '';
    $('c-host').value = char ? char.host : '3k.org';
    $('c-port').value = char ? String(char.port) : '3000';
    $('c-password').value = '';
    $('c-remember').checked = !!(char && char.has_password);
    $('c-note').value = (char && char.note) || '';
    $('c-password-hint').textContent = char && char.has_password
      ? 'One is saved. Leave blank to keep it; untick below to forget it.'
      : 'Leave blank and the client will ask each time you play.';
    if (show) $('c-name').focus();
  }

  $('char-add').onclick = () => form(null, true);
  $('char-cancel').onclick = () => form(null, false);

  $('char-form').onsubmit = (e) => {
    e.preventDefault();
    const name = $('c-name').value.trim();
    if (!name) {
      $('char-error').textContent = 'a character needs a name';
      return;
    }
    send({
      op: 'save',
      character: {
        name: editing ? editing.name : name,
        host: $('c-host').value.trim(),
        port: parseInt($('c-port').value, 10) || 3000,
        password: $('c-password').value,
        remember: $('c-remember').checked,
        note: $('c-note').value.trim(),
      },
    });
    form(null, false);
  };

  // --- the list -------------------------------------------------------------

  function button(text, cls, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    if (cls) b.className = cls;
    b.onclick = fn;
    return b;
  }

  function play(char, password, remember) {
    send({ op: 'play', name: char.name, password, remember });
  }

  /* Will picking a name put us into the game, rather than only load their
     settings?  True at the prompt, and true after a hang-up -- where there is
     no prompt yet because there is no connection, and choosing is what makes
     one. */
  function playing() {
    return who.asking || who.offline;
  }

  function card(char) {
    const el = document.createElement('div');
    el.className = 'char' + (who.character === char.name ? ' on' : '');

    const box = document.createElement('div');
    box.className = 'who';
    const nm = document.createElement('div');
    nm.className = 'nm';
    nm.textContent = char.name;
    const sub = document.createElement('div');
    sub.className = 'sub';
    sub.textContent = [
      `${char.host}:${char.port}`,
      char.has_password ? 'password saved' : '',
      char.note,
      who.character === char.name ? 'playing' : '',
    ].filter(Boolean).join('  ·  ');
    box.append(nm, sub);

    const acts = document.createElement('span');
    acts.className = 'acts';
    acts.append(
      button(playing() ? 'Play' : 'Load settings', 'primary', () => {
        // No saved password and one is going to be wanted: ask here rather
        // than sending a name the game will then sit waiting on.
        if (playing() && !char.has_password) ask(el, char);
        else play(char, '', false);
      }),
      button('Edit', '', () => form(char, true)),
      button('×', '', () => {
        if (confirm(`Forget ${char.name}?`)) send({ op: 'forget', name: char.name });
      }),
    );

    el.append(box, acts);
    return el;
  }

  function ask(el, char) {
    if (el.querySelector('.ask')) return;
    const row = document.createElement('form');
    row.className = 'ask';
    const pw = document.createElement('input');
    pw.type = 'password';
    pw.placeholder = `${char.name}'s password`;
    const keep = document.createElement('label');
    keep.className = 'check';
    const box = document.createElement('input');
    box.type = 'checkbox';
    keep.append(box, document.createTextNode('remember'));
    const go = document.createElement('button');
    go.type = 'submit';
    go.className = 'primary';
    go.textContent = 'Play';
    row.append(pw, keep, go);
    row.onsubmit = (e) => {
      e.preventDefault();
      play(char, pw.value, box.checked);
    };
    el.append(row);
    pw.focus();
  }

  function render() {
    const list = $('char-list');
    list.replaceChildren();
    for (const c of who.known) list.append(card(c));

    $('login-state').textContent = who.offline
      ? 'Disconnected. Pick a character and the client will connect and log '
        + 'them in.'
      : who.character
      ? `Playing ${who.character}. Their triggers, aliases and markers are `
        + 'loaded; the map and routes are shared with everyone.'
      : who.asking
        ? 'The MUD is asking for a name. Pick one and the client will answer.'
        : who.known.length
          ? 'Pick one to load their triggers, aliases and markers.'
          : 'Add a character and the client will remember their triggers, '
            + 'aliases and line markers separately from everyone else’s.';

    const btn = $('open-login');
    btn.textContent = who.character || 'No character';
    btn.classList.toggle('on', !!who.character);

    // The markers button writes to whoever is loaded, so the panel says who.
    $('setup-who').textContent = who.character
      ? `These are ${who.character}'s.`
      : 'No character loaded — these go to whoever is logged in.';

    // It shows itself while nobody has said who is playing, and gets out of
    // the way the moment somebody has -- by picking a name, by skipping, or
    // by typing their own name past it.  Once opened on purpose it stays
    // until it is closed on purpose.
    if (!forced) $('login').hidden = !who.needed;
  }

  let last = '';
  window.renderWho = function (state) {
    if (!state) return;
    // The snapshot arrives several times a second and this rebuilds the whole
    // list.  Rebuilding it under the cursor replaces the button between the
    // press and the release, and the click lands on nothing -- so redraw only
    // when something has actually changed.
    const key = JSON.stringify(state);
    if (key === last) return;
    last = key;
    who = state;
    render();
  };

  window.handleLogin = function (m) {
    if (m.op === 'error') $('char-error').textContent = m.error;
  };
})();
