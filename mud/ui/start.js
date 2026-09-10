/* Options -> Getting started: the things worth doing once per character.

   A new player used to get the map and nothing else -- the markers the mapper
   leans on were two clicks under Character setup, and saving their own colours
   only helps before those go on.  This page puts them in order, works out for
   itself which are done, and opens on its own the first time a character logs
   in.  Nothing here is sent to the character without a click. */

(function () {
  const $ = (id) => document.getElementById(id);
  let state = null;
  let opened = false;           // opened by itself already, this window
  let poll = null;

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'start', ...msg }));
    }
  }

  window.refreshStart = () => {
    send({ op: 'state' });
    // While the page is open its steps tick themselves: a marked title
    // arriving, the fetch finishing.
    clearInterval(poll);
    poll = setInterval(() => {
      const pane = document.querySelector(".opt-pane[data-pane='start']");
      if (!pane || pane.hidden || $('options').hidden) {
        clearInterval(poll);
        poll = null;
        return;
      }
      send({ op: 'state' });
    }, 2000);
  };

  function step(id, done, said, warn) {
    const li = $(id);
    li.classList.toggle('ok', !!done);
    li.classList.toggle('warn', !!warn && !done);
    li.querySelector('.gs-state').textContent = said;
  }

  function render() {
    if (!state) return;
    $('gs-who').textContent = state.who ? `for ${state.who}` : '';
    const d = state.data || {};
    step('gs-data', d.rooms > 0 && !d.fetching,
      d.fetching ? (d.said || 'fetching…')
        : d.rooms ? `${d.rooms.toLocaleString()} rooms, ${d.routes} routes, `
          + `${d.gag_groups} gag groups`
          : (d.said || 'not fetched yet — Options → Updates'),
      !d.fetching && !d.rooms);

    const c = state.colours || {};
    const own = c.own;
    step('gs-colours', !!own, own ? `saved ${own.when}`
      : c.latest ? 'saved, but with the markers already in'
        : 'not saved — only matters if you might go back to another client');

    const m = state.markers;
    step('gs-markers', m === 'on',
      m === 'on' ? 'on' : m === 'off' ? 'off — the map finds you far less often'
        : 'walk a room or two and it will say', m === 'off');

    const b = state.brief;
    step('gs-brief', !!b, b
      ? `${b.brief === 'on' ? 'short' : 'long'} descriptions, minimap ${b.mapping === 'yes' ? 'shown' : 'hidden'}`
      : 'asked at login');

    step('gs-extras', state.gags_on > 0,
      state.gags_on ? `${state.gags_on} gag group${state.gags_on === 1 ? '' : 's'} on` : 'optional');

    $('gs-done').textContent = state.done ? 'Show again at login' : 'Done';
    if (window.options) {
      const left = ['gs-data', 'gs-markers'].filter((id) => !$(id).classList.contains('ok'));
      window.options.count('start', state.done ? 0 : left.length);
    }
  }

  window.handleStart = function (m) {
    if (m.op !== 'state') return;
    state = m;
    render();
  };

  /* Opens itself once per window: a character playing, MIP flowing, the
     character screen out of the way, and not marked done for them. */
  window.maybeGetStarted = function (s) {
    if (!s || opened || s.done || !s.live) return;
    if ($('login') && !$('login').hidden) return;
    opened = true;
    if (window.options) window.options.open('start');
  };

  $('gs-colours-save').onclick = () => {
    if (window.sendCommand) window.sendCommand('/ansivars');
  };

  // Show first, then send -- the same two clicks as Character setup.
  $('gs-markers-set').onclick = () => {
    const b = $('gs-markers-set');
    const armed = b.dataset.armed === '1';
    if (window.sendCommand) window.sendCommand(armed ? '/prefixes set' : '/prefixes');
    b.dataset.armed = armed ? '' : '1';
    b.textContent = armed ? 'Set line markers' : 'Send them — click again';
    if (!armed) {
      setTimeout(() => { b.dataset.armed = ''; b.textContent = 'Set line markers'; }, 20000);
    }
  };

  for (const b of document.querySelectorAll('#gs-steps [data-go]')) {
    b.onclick = () => { if (window.options) window.options.show(b.dataset.go); };
  }

  $('gs-done').onclick = () => {
    send({ op: 'done', on: !(state && state.done) });
    if (!(state && state.done) && window.options) window.options.close();
  };
})();
