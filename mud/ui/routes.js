/* Routes & hunts: name it, paste a path, say what to kill.

   The whole of a tt++ botpath is a name and a list of directions, so it is a
   form rather than a file.  A route runs once and stops at the end unless you
   tick repeat -- a route that quietly starts over is one still walking your
   character around an hour after you stopped watching. */

(function () {
  const $ = (id) => document.getElementById(id);
  let routes = [];
  //: a /go or map-click walk, if one is going: shown in the Bot panel
  let walk = null;

  //: set while a save is in flight, so the list coming back closes the form
  let saving = false;

  function send(msg) {
    if (window.ws) window.ws.send(JSON.stringify({ t: 'routes', ...msg }));
  }

  //: opening the routes tab is when to ask the server for the current set
  window.refreshRoutes = () => send({ op: 'list' });

  /* Everything about a route somebody might search for.

     The path included, because with sixty-seven of them imported from tt++
     the thing you remember is often a step rather than a name -- "the one
     that starts with embrace void". */
  function matches(r) {
    const q = window.options ? window.options.query() : '';
    if (!q) return true;
    const hay = [r.name, r.path, r.setup, r.note, r.start,
                 ...(r.targets || [])]
      .filter(Boolean).join(' \u0000 ').toLowerCase();
    return q.split(/\s+/).every((word) => hay.includes(word));
  }

  // --- the form -------------------------------------------------------------

  function edit(route) {
    if (window.options) window.options.editor('route-editor');
    $('route-form-title').textContent = route ? `Edit ${route.name}` : 'New route';
    $('r-id').value = route ? route.id : '';
    $('r-name').value = route ? route.name : '';
    $('r-path').value = route ? route.path : '';
    $('r-setup').value = route ? (route.setup || '') : '';
    $('r-targets').value = route ? (route.targets || []).join(', ') : '';
    $('r-loop').checked = route ? !!route.loop : false;
    $('r-polite').checked = route ? !!route.polite : false;
    $('r-start').value = route && route.start ? String(route.start) : '';
    $('r-group').value = route ? (route.group || '') : '';
    $('r-rest').value = route ? String(route.rest || 0) : '0';
    $('route-error').textContent = '';
    $('r-name').focus();
  }

  function closeForm() {
    if (window.options) window.options.editor(null);
  }

  $('r-new').onclick = () => edit(null);
  $('route-back').onclick = closeForm;
  $('route-cancel').onclick = closeForm;

  $('route-form').addEventListener('submit', (e) => {
    e.preventDefault();
    saving = true;
    send({
      op: 'save',
      route: {
        id: $('r-id').value,
        name: $('r-name').value,
        path: $('r-path').value,
        setup: $('r-setup').value,
        targets: $('r-targets').value,
        loop: $('r-loop').checked,
        polite: $('r-polite').checked,
        group: $('r-group').value,
        start: parseInt($('r-start').value, 10) || 0,
        rest: parseFloat($('r-rest').value) || 0,
      },
    });
  });

  $('route-stop-all').onclick = () => send({ op: 'stop_all' });

  // --- the list -------------------------------------------------------------

  function button(text, cls, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    if (cls) b.className = cls;
    b.onclick = fn;
    return b;
  }

  function render() {
    const q = window.options ? window.options.query() : '';
    const list = $('route-list');
    list.replaceChildren();
    list.dataset.empty = q
      ? `No route matches “${q}”.`
      : list.dataset.none || 'No routes yet.';
    const shown = routes.filter(matches);
    const card = function (r) {
      const row = document.createElement('div');
      row.className = 'route' + (r.running ? ' running' : '');

      const top = document.createElement('div');
      top.className = 'top';
      const nm = document.createElement('span');
      nm.className = 'nm';
      nm.textContent = r.name;
      top.append(
        nm,
        button(r.running ? 'Stop' : 'Walk', 'go',
               () => send({ op: r.running ? 'stop' : 'start', id: r.id })),
        button('Edit', '', () => edit(r)),
        button('×', '', () => send({ op: 'delete', id: r.id })),
      );

      const meta = document.createElement('div');
      meta.className = 'meta';
      const bits = [`${r.step_count} step${r.step_count === 1 ? '' : 's'}`];
      if (r.loop) bits.push('repeats');
      if (r.start) bits.push(`from #${r.start}`);
      if (r.polite) bits.push('polite');
      if (r.targets && r.targets.length) bits.push('kills ' + r.targets.join(', '));
      if (r.running || r.steps_taken) {
        bits.push(`${r.steps_taken} walked`);
        if (r.kills) bits.push(`${r.kills} killed`);
      }
      if (r.note) bits.push(r.note);
      meta.textContent = bits.join('  ·  ');

      row.append(top, meta);
      return row;
    };

    // A search flattens the folders: what you are looking for should not be
    // behind one that happens to be folded away.
    if (q) {
      list.append(...shown.map(card));
    } else {
      list.append(...window.folderTree({
        key: 'routes',
        items: shown,
        folderOf: (r) => r.group || '',
        card: card,
        onRename: (from, to) => send({ op: 'rename_folder', from, to }),
        redraw: render,
      }));
    }

    // What is walking, and what is paused, in the sidebar's Bot panel.
    const walking = routes.filter((r) => r.running);
    if (window.renderBotPanel) window.renderBotPanel(routes, walk);

    const btn = $('open-options');
    btn.classList.toggle('live', walking.length > 0);
    btn.textContent = walking.length
      ? `Options \u00b7 ${walking.length} walking` : 'Options';
    if (window.renderFolders) window.renderFolders();
    if (window.options) {
      window.options.count('routes', routes.length);
      window.options.note(walking.map((r) => r.name).join(', '));
    }
  }

  //: redraw from what we already have -- searching asks the server nothing
  window.renderRoutes = render;
  window.allRoutes = () => routes || [];

  window.handleRoutes = function (m) {
    if (m.op === 'error') {
      saving = false;
      $('route-error').textContent = m.error;
      return;
    }
    if (m.op === 'list') {
      routes = m.routes || [];
      walk = m.walk || null;
      // The folders there are, to pick from rather than retype -- and typing
      // a new one is still how a new folder is made.
      $('r-folders').replaceChildren(...(m.folders || []).map((f) => {
        const o = document.createElement('option');
        o.value = f;
        return o;
      }));
      if (window.setAutoCollect) window.setAutoCollect(!!m.autocollect);
      // The form closes only once the server has taken the save: an error
      // comes back on the same channel, and closing on the click would throw
      // away what you typed before you had seen why it was refused.
      if (saving) {
        saving = false;
        closeForm();
      }
      render();
    }
  };
})();
