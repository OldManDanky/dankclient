/* The Bot panel: find a route, start it, pause it, stop it -- without opening
   Options.

   Pause is not stop.  It keeps the step the route had reached and the room
   that left it in; Resume walks back to that room, does what the route does
   there, and carries on from the next step.  Stop forgets all of that.

   Only one route walks at a time from here.  While one is walking the panel
   shows it and nothing else can be started: two routes driving one character
   are two routes each walking from a room the other has just left.

   With a hundred routes imported from 3kdb a list would be a wall, so it is a
   search, like Options: part of a name, a step or a creature. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;
  const MOST = 8;

  let routes = [];
  //: a /go or map-click walk the server says is going
  let walk = null;
  let chosen = store ? store.get('bot:route', '') : '';
  //: what the results were last drawn from, so a step taken does not rebuild
  //: the buttons under the cursor
  let drawn = '';

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'routes', ...msg }));
    }
  }

  function hay(r) {
    return [r.name, r.path, r.setup, ...(r.targets || [])]
      .filter(Boolean).join('   ').toLowerCase();
  }

  function found(q) {
    const want = q.toLowerCase().split(/\s+/).filter(Boolean);
    return routes.filter((r) => want.every((w) => hay(r).includes(w)));
  }

  const walking = () => routes.find((r) => r.running) || null;
  const walkingTo = () => (walk && walk.running ? walk : null);
  //: what stops anything else being started: a route, or a walk
  const busyWith = () => walking()
    || (walkingTo() ? { id: '__walk', name: 'A walk' } : null);

  /* The one the panel is about: whatever is walking, else the one picked,
     else one that is paused. */
  function current() {
    return walking() || routes.find((r) => r.id === chosen)
      || routes.find((r) => r.paused) || null;
  }

  function choose(r) {
    chosen = r.id;
    if (store) store.set('bot:route', chosen);
    $('bot-find').value = '';
    draw();
  }

  function button(text, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.onclick = fn;
    return b;
  }

  // --- what it is doing -------------------------------------------------------

  function drawNow() {
    // A /go or a click on the map: where to, and Stop.  Nothing to pause --
    // it is a stack, already sent.
    const w = walkingTo();
    if (w && !walking()) {
      $('bot-name').textContent = w.goal ? `Walking to ${w.goal}` : 'Walking';
      $('bot-step').textContent = w.steps ? `${w.steps} step${w.steps === 1 ? '' : 's'}` : '';
      $('bot-bar').style.width = '100%';
      $('bot-now').className = 'live';
      $('bot-note').textContent = w.note || '';
      $('bot-start').textContent = 'Start';
      $('bot-start').disabled = true;
      $('bot-pause').textContent = 'Pause';
      $('bot-pause').disabled = true;
      $('bot-stop').disabled = false;
      return;
    }
    const r = current();
    const all = r ? r.step_count || 0 : 0;
    const done = r ? r.steps_taken || 0 : 0;
    let at = 0;
    if (r && r.paused) at = r.paused.step || 0;
    else if (r && r.running) at = r.loop && all ? done % all : done;

    $('bot-name').textContent = r ? r.name : 'No bot chosen';
    $('bot-step').textContent = !r ? ''
      : r.running || r.paused ? `${at} / ${all}` : `${all} step${all === 1 ? '' : 's'}`;
    // A repeating route walks past its own length, so the bar shows where it
    // is in the current lap rather than filling up and staying full.
    $('bot-bar').style.width = (all ? Math.min(100, (at / all) * 100) : 0) + '%';
    $('bot-now').className = r && r.running ? 'live' : r && r.paused ? 'held' : '';

    const bits = [];
    if (r && r.paused) {
      bits.push(r.paused.room_name ? `paused in ${r.paused.room_name}`
        : r.paused.room ? `paused in room #${r.paused.room}`
          : 'paused — the map did not know where, so it resumes from where you stand');
    }
    if (r && (r.running || r.paused) && r.kills) bits.push(`${r.kills} killed`);
    if (r && r.running && r.loop) bits.push(`lap ${Math.floor(done / Math.max(1, all)) + 1}`);
    if (r && r.note && !(r.paused && r.note.startsWith('paused at'))) bits.push(r.note);
    $('bot-note').textContent = bits.join('  ·  ');

    const start = $('bot-start');
    start.textContent = r && r.paused ? 'Start over' : 'Start';
    start.disabled = !r || !!r.running;
    const pause = $('bot-pause');
    pause.textContent = r && r.paused ? 'Resume' : 'Pause';
    pause.disabled = !r || (!r.running && !r.paused);
    $('bot-stop').disabled = !r || (!r.running && !r.paused);
  }

  // --- finding one ------------------------------------------------------------

  function drawFound() {
    const q = $('bot-find').value.trim();
    const hits = q ? found(q) : [];
    const busy = busyWith();
    const key = JSON.stringify([q, busy && busy.id,
      hits.slice(0, MOST).map((r) => [r.id, r.name, r.step_count])]);
    if (key === drawn) return;
    drawn = key;

    const box = $('bot-found');
    box.replaceChildren();
    box.hidden = !q;
    if (!q) return;
    if (!hits.length) {
      const none = document.createElement('p');
      none.className = 'bf-none';
      none.textContent = `No bot matches “${q}”.`;
      box.append(none);
      return;
    }
    for (const r of hits.slice(0, MOST)) {
      const row = document.createElement('div');
      row.className = 'bf';
      const name = button(r.name, () => choose(r));
      name.className = 'bf-name';
      name.title = 'Show it here without starting it';
      const meta = document.createElement('span');
      meta.className = 'bf-meta';
      meta.textContent = `${r.step_count} steps`
        + (r.targets && r.targets.length ? ` · ${r.targets.join(', ')}` : '');
      const go = button(r.paused ? 'Resume' : 'Start', () => {
        choose(r);
        send({ op: r.paused ? 'resume' : 'start', id: r.id });
      });
      go.className = 'bf-go';
      go.disabled = !!busy;
      if (busy) go.title = `${busy.name} is walking — stop or pause it first`;
      row.append(name, meta, go);
      box.append(row);
    }
    if (hits.length > MOST) {
      const more = document.createElement('p');
      more.className = 'bf-none';
      more.textContent = `and ${hits.length - MOST} more — keep typing`;
      box.append(more);
    }
  }

  function draw() {
    drawNow();
    drawFound();
  }

  // --- the buttons ------------------------------------------------------------

  $('bot-start').onclick = () => {
    const r = current();
    if (r && !r.running) send({ op: 'start', id: r.id });
  };
  $('bot-pause').onclick = () => {
    const r = current();
    if (r) send({ op: r.paused ? 'resume' : 'pause', id: r.id });
  };
  $('bot-stop').onclick = () => {
    if (walkingTo() && !walking()) {
      send({ op: 'stop_walk' });
      return;
    }
    const r = current();
    if (r) send({ op: 'stop', id: r.id });
  };
  $('bot-find').oninput = drawFound;
  $('bot-find').onkeydown = (e) => {
    if (e.key === 'Escape') {
      $('bot-find').value = '';
      drawFound();
    } else if (e.key === 'Enter') {
      // Picks the first, and does not start it: Enter is the key most often
      // pressed by accident, and a start is a character walking off.
      e.preventDefault();
      const first = found($('bot-find').value.trim())[0];
      if (first) choose(first);
    }
  };

  window.renderBotPanel = function (list, w) {
    routes = list || [];
    walk = w || null;
    draw();
  };
  draw();
})();
