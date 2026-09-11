/* Options -> From TinTin++ / zMUD: pick .tin files or a zMUD settings
   export, see what each thing in them
   becomes, and bring in what you tick.

   The files are read here and sent to the server as text; ttimport.py does
   the reading, twice -- once to show, once to import what was ticked -- so
   what is imported is exactly what was shown.  Nothing is added until
   Import is pressed, and anything already there is left unticked. */

(function () {
  const $ = (id) => document.getElementById(id);
  const KINDS = [['alias', 'Aliases'], ['trigger', 'Triggers'], ['gag', 'Gags'], ['timer', 'Timers'],
    ['route', 'Routes']];
  let files = [];
  let items = [];

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'ttimport' }, msg)));
    }
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // --- reading the files ---------------------------------------------------------

  function read(list) {
    const chosen = [...(list || [])];
    if (!chosen.length) return;
    let left = chosen.length;
    const got = [];
    for (const f of chosen) {
      const r = new FileReader();
      r.onload = () => {
        got.push({ name: f.name, text: String(r.result || '') });
        if (--left === 0) {
          // In the order a folder lists them, so line numbers read sensibly.
          files = got.sort((a, b) => a.name.localeCompare(b.name));
          $('tt-said').textContent = '';
          send({ op: 'read', files });
        }
      };
      r.readAsText(f);
    }
  }

  // --- what it found ---------------------------------------------------------------

  /* What a rule does, in one line, the way the rule lists say it. */
  function says(it) {
    const r = it.rule || {};
    const acts = (r.actions || []).map((a) => (a.type === 'wait' ? `wait ${a.text}s`
      : a.type === 'log' ? `show "${a.text}"` : a.text)).join(' ; ');
    if (it.kind === 'gag') return `hide lines ${r.mode === 'contains' ? 'containing' : 'matching'} ${r.pattern}`;
    if (it.kind === 'timer') return `every ${r.every}s: ${acts}`;
    if (it.kind === 'route') {
      return `route ${r.name}: ${r.path.length > 160 ? r.path.slice(0, 160) + '\u2026' : r.path}`
        + (r.start ? `  (starts at room ${r.start})` : '');
    }
    const what = r.mode === 'command' ? r.pattern : `${r.mode} ${r.pattern}`;
    return `${what}  →  ${acts}`;
  }

  function row(it, box) {
    const line = el('label', 'tt-item' + (it.have ? ' have' : ''));
    const tick = el('input');
    tick.type = 'checkbox';
    tick.checked = !it.have;
    tick.dataset.id = String(it.id);
    tick.onchange = count;
    line.append(tick, el('span', 'from', `${it.source}  ${it.text}`));
    line.append(el('span', 'to', says(it)));
    const notes = [...(it.notes || [])];
    if (it.have) notes.unshift('you already have this; ticking it adds nothing');
    if (notes.length) line.append(el('span', 'note', notes.join(' · ')));
    box.append(line);
  }

  function chosen() {
    return [...$('tt-list').querySelectorAll('input[type=checkbox]')]
      .filter((c) => c.checked).map((c) => Number(c.dataset.id));
  }

  function count() {
    const n = chosen().length;
    $('tt-import').textContent = n ? `Import ${n}` : 'Import';
    $('tt-import').disabled = !n;
  }

  function draw() {
    $('tt-result').hidden = false;
    const list = $('tt-list');
    list.replaceChildren();
    const by = (k) => items.filter((it) => it.kind === k);
    const parts = [];
    for (const [kind, label] of KINDS) {
      const these = by(kind);
      if (!these.length) continue;
      parts.push(`${these.length} ${label.toLowerCase()}`);
      const head = el('div', 'tt-kind', `${label} (${these.length})`);
      const none = el('button', '', 'none');
      none.type = 'button';
      none.onclick = () => {
        const boxes = [...list.querySelectorAll('input[type=checkbox]')]
          .filter((c) => these.some((it) => String(it.id) === c.dataset.id));
        const on = !boxes.every((c) => c.checked);
        boxes.forEach((c) => { c.checked = on; });
        none.textContent = on ? 'none' : 'all';
        count();
      };
      head.append(none);
      list.append(head);
      for (const it of these) row(it, list);
    }
    const skipped = by('skip');
    const summary = $('tt-summary');
    summary.replaceChildren();
    summary.append(el('b', '', parts.join(', ') || 'Nothing that comes across'),
      document.createTextNode(skipped.length ? ` — and ${skipped.length} that do not.` : '.'));
    $('tt-skipped').hidden = !skipped.length;
    $('tt-skipped').querySelector('summary').textContent = `Not brought across (${skipped.length})`;
    const why = $('tt-skip-list');
    why.replaceChildren();
    for (const it of skipped) {
      const line = el('div', 'tt-item');
      line.append(el('span', 'from', `${it.source}  ${it.text}`), el('span', 'note', it.why));
      why.append(line);
    }
    count();
  }

  window.handleTTImport = function (m) {
    if (m.op === 'read') {
      items = m.items || [];
      draw();
    } else if (m.op === 'done') {
      const group = 'tintin';
      $('tt-said').textContent = `Added ${m.added}.`
        + (m.added ? ` They are in their #class groups, or "${group}" — /group ${group} off switches those off.` : '')
        + (m.problems && m.problems.length ? ` Not added: ${m.problems.join('; ')}` : '');
      // Read again, so what is now there shows as there.
      if (files.length) send({ op: 'read', files });
      if (window.refreshRules) window.refreshRules();
    } else if (m.op === 'error') {
      $('tt-said').textContent = m.error;
    }
  };

  if ($('tt-pick')) $('tt-pick').onclick = () => $('tt-files').click();
  if ($('tt-files')) $('tt-files').onchange = () => read($('tt-files').files);
  if ($('tt-import')) {
    $('tt-import').onclick = () => {
      const ids = chosen();
      if (ids.length) send({ op: 'import', files, ids });
    };
  }
})();
