/* The Folders pane: everything filed under one name, whatever kind it is.
 *
 * A folder has always been able to span kinds -- a rule's group is on every
 * kind of rule, and `/group zodiacs off` has switched triggers, aliases,
 * timers and stat watches together since groups existed.  What was missing
 * was somewhere to *see* that: the five rule panes are five filtered views of
 * one store, so an area's triggers were in one, its aliases in another, and
 * its route in a store of its own.
 *
 * Two screens, not two columns: the folders, and then one folder.  Options
 * already has a rail, so a tree beside it would be a third column and would
 * have to become something else on a phone anyway.
 *
 * It owns no data.  The census is built from the rules and routes the page
 * already holds, so this pane and the lists it summarises cannot disagree;
 * what it cannot do here is write, and both writes -- switching and renaming
 * -- have to reach both stores, so those go to the server.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  // Plural and singular given outright.  Taking the "s" off was worth one
  // bug: "Routes" became "1 rout", and "Stat watches" would have been worse.
  const KINDS = [
    ['trigger', 'Triggers', 'trigger'], ['alias', 'Aliases', 'alias'],
    ['event', 'Events', 'event'], ['watch', 'Stat watches', 'stat watch'],
    ['timer', 'Timers', 'timer'], ['route', 'Routes', 'route'],
  ];
  //: which folder is open, or null for the list of them
  let open = null;

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'folders' }, msg)));
    }
  }

  function items() {
    const rules = (window.allRules ? window.allRules() : [])
      .filter((r) => r.group)
      .map((r) => Object.assign({}, r, { fkind: r.kind }));
    const routes = (window.allRoutes ? window.allRoutes() : [])
      .filter((r) => r.group)
      .map((r) => Object.assign({}, r, { fkind: 'route' }));
    return rules.concat(routes);
  }

  /* Every folder, with what is in it -- and, rolled up, what is in the
     folders under it, because "what do I have for this area" includes them. */
  function census(all) {
    const found = new Map();
    const put = (path) => {
      const parts = path.split('/');
      for (let n = 1; n <= parts.length; n += 1) {
        const at = parts.slice(0, n).join('/');
        const key = at.toLowerCase();
        if (!found.has(key)) found.set(key, { path: at, own: [] });
      }
      return found.get(path.toLowerCase());
    };
    for (const item of all) put(item.group).own.push(item);
    const rows = [...found.values()];
    for (const row of rows) {
      const low = row.path.toLowerCase() + '/';
      row.deep = row.own.slice();
      for (const other of rows) {
        if (other.path.toLowerCase().startsWith(low)) {
          row.deep = row.deep.concat(other.own);
        }
      }
      row.on = row.deep.filter((i) => i.enabled !== false).length;
    }
    rows.sort((a, b) => a.path.toLowerCase().localeCompare(b.path.toLowerCase()));
    return rows;
  }

  function tally(list) {
    const out = [];
    for (const [kind, label, one] of KINDS) {
      const n = list.filter((i) => i.fkind === kind).length;
      if (n) out.push(`${n} ${n === 1 ? one : label.toLowerCase()}`);
    }
    return out.join(' · ');
  }

  /* The switch, on a button that already exists or a new one.  The pane's own
     switch is dressed rather than replaced: swapping the element out meant
     putting its id back on the new one every draw, which is a way to lose
     both the id and whatever else was listening. */
  function dressSwitch(b, row) {
    const allOn = row.deep.length > 0 && row.on === row.deep.length;
    b.type = 'button';
    b.textContent = allOn ? 'turn off' : 'turn on';
    b.title = `/group ${row.path} ${allOn ? 'off' : 'on'} does the same from `
      + 'the input line, and switches its routes with them';
    b.onclick = (e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      send({ op: 'set', name: row.path, on: !allOn });
    };
    return b;
  }

  function switchButton(row) {
    return dressSwitch(document.createElement('button'), row);
  }

  /* --- the list of folders ------------------------------------------------ */

  function indexRow(row) {
    const el = document.createElement('div');
    el.className = 'fold-row';
    const name = document.createElement('b');
    name.textContent = row.path;
    const what = document.createElement('span');
    what.className = 'meta';
    what.textContent = tally(row.deep)
      + (row.on === row.deep.length ? '' : `  ·  ${row.on} of ${row.deep.length} on`);
    el.append(name, what, switchButton(row));
    el.tabIndex = 0;
    el.onclick = () => { open = row.path; render(); };
    el.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') { open = row.path; render(); }
    };
    return el;
  }

  /* --- one folder --------------------------------------------------------- */

  function itemRow(item) {
    const el = document.createElement('div');
    el.className = 'fold-item' + (item.enabled === false ? ' off' : '');
    const titled = item.fkind === 'route' ? item.name
      : (item.name || item.pattern || '(no pattern)');
    const name = document.createElement('b');
    name.textContent = titled;
    const where = document.createElement('span');
    where.className = 'meta';
    // The folder's own name next to every item in it says nothing.  What is
    // worth the room is what the thing does -- and the path only when it is
    // somewhere else, which is how an item from a folder underneath reads.
    where.textContent = item.group === open ? says(item, titled) : item.group;
    const go = document.createElement('button');
    go.type = 'button';
    go.textContent = 'Show';
    go.title = item.fkind === 'route' ? 'Open it in Routes & bots'
      : 'Open it in its own page';
    go.onclick = () => {
      if (!window.options) return;
      window.options.open(item.fkind === 'route' ? 'routes' : item.fkind);
    };
    el.append(name, where, go);
    return el;
  }

  /* A line about the thing itself, in the words its own pane uses. */
  function says(item, titled) {
    if (item.fkind === 'route') {
      const n = item.step_count || 0;
      return `${n} step${n === 1 ? '' : 's'}`
        + (item.targets && item.targets.length
           ? `  \u00b7  kills ${item.targets.join(', ')}` : '');
    }
    const first = (item.actions || [])[0];
    const did = !first ? ''
      : first.type === 'wait' ? `wait ${first.text}s`
      : first.type === 'log' ? 'to the log'
      : first.text || '';
    const more = (item.actions || []).length > 1
      ? `  \u00b7  +${item.actions.length - 1} more` : '';
    if (item.fkind === 'timer') return `every ${item.every}s \u2192 ${did}${more}`;
    if (item.fkind === 'watch') {
      return `${item.watch_field} ${item.value} \u2192 ${did}${more}`;
    }
    if (item.fkind === 'event') return `on ${item.event} \u2192 ${did}${more}`;
    // The title is the pattern when a rule has no name of its own, and
    // printing it twice on one line is worse than printing it once.
    return item.pattern && item.pattern !== titled
      ? `${item.pattern} \u2192 ${did}${more}` : `${did}${more}`;
  }

  function heading(text) {
    const el = document.createElement('div');
    el.className = 'folder';
    const b = document.createElement('b');
    b.textContent = text;
    el.append(b);
    return el;
  }

  function render() {
    const list = $('fold-list');
    if (!list) return;
    const rows = census(items());
    if (window.options) window.options.count('folders', rows.length);

    const here = open && rows.find((r) => r.path === open);
    if (open && !here) open = null;          // its last item left it

    $('fold-back').hidden = !open;
    $('fold-switch').hidden = true;
    $('fold-rename').hidden = !open;
    list.replaceChildren();

    if (!open) {
      $('fold-title').textContent = 'Folders';
      $('fold-blurb').textContent = 'Everything you have filed under one '
        + 'name, whatever kind it is. Choose one to see what is in it.';
      list.append(...rows.map(indexRow));
      return;
    }

    $('fold-title').textContent = here.path;
    $('fold-blurb').textContent = `${here.deep.length} thing`
      + `${here.deep.length === 1 ? '' : 's'} here, ${here.on} on`
      + (here.deep.length > here.own.length
         ? ` — including what is in the folders under it` : '');
    const sw = dressSwitch($('fold-switch'), here);
    sw.hidden = false;

    for (const [kind, label] of KINDS) {
      const mine = here.own.filter((i) => i.fkind === kind);
      if (!mine.length) continue;
      list.append(heading(`${label} (${mine.length})`));
      list.append(...mine.map(itemRow));
    }
    const under = rows.filter((r) => r.path.toLowerCase()
      .startsWith(here.path.toLowerCase() + '/'));
    if (under.length) {
      list.append(heading('In here'));
      list.append(...under.map(indexRow));
    }
  }

  $('fold-back').onclick = () => { open = null; render(); };
  $('fold-rename').onclick = () => {
    if (!open) return;
    const want = window.prompt('Folder name (a / makes another level, an '
      + 'empty name files everything at the top):', open);
    if (want === null || want === open) return;
    send({ op: 'rename', from: open, to: want });
    open = want.trim() ? want.trim() : null;
  };

  window.renderFolders = render;
  window.handleFolders = function (m) {
    // Writing is the server's; it answers by sending both lists again, and
    // their own handlers call back in here.  Only an error lands.
    if (m.op === 'error' && window.options) window.options.note(m.error);
  };
  render();
})();
