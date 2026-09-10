/* Options -> Marks: every place /go knows by name, how far each is from where
   you stand, and a button to go there.

   The same list as /speedruns, for somebody who would rather look than type.
   Distances are from wherever you were when the tab opened -- one search out
   from there on the server -- and Update works them out again after you have
   moved.  Searchable with the box at the top of Options, like every list. */

(function () {
  const $ = (id) => document.getElementById(id);
  const KINDS = { area: 'area', mob: 'mob', crafting: 'crafting', shop: 'shop',
    eq: 'equipment', clan: 'clan hall', item: 'item', misc: 'other' };
  const MOST = 400;
  let marks = [];
  let lost = false;

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'marks', ...msg }));
    }
  }

  window.refreshMarks = () => {
    $('marks-now').textContent = 'Working out how far each one is…';
    send({ op: 'list' });
  };

  function matches(m, q) {
    if (!q) return true;
    const hay = `${m.name} ${m.note} ${KINDS[m.kind] || m.kind}`.toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w));
  }

  function nearest(a, b) {
    return (a.steps == null) - (b.steps == null)
      || (a.steps || 0) - (b.steps || 0) || a.name.localeCompare(b.name);
  }

  function render() {
    const q = window.options ? window.options.query() : '';
    const list = $('marks-list');
    list.replaceChildren();
    list.dataset.empty = q ? `No mark matches “${q}”.` : list.dataset.none;
    for (const m of marks.filter((x) => matches(x, q)).sort(nearest).slice(0, MOST)) {
      const far = !lost && m.steps == null;
      const row = document.createElement('div');
      row.className = 'route' + (far ? ' far' : '');
      const top = document.createElement('div');
      top.className = 'top';
      const name = document.createElement('span');
      name.className = 'nm';
      name.textContent = m.name;
      const kind = document.createElement('span');
      kind.className = 'tag';
      kind.textContent = KINDS[m.kind] || m.kind;
      const dist = document.createElement('span');
      dist.className = 'dist';
      dist.textContent = lost ? '' : far ? 'can’t reach'
        : m.steps === 0 ? 'here' : `${m.steps} step${m.steps === 1 ? '' : 's'}`;
      const go = document.createElement('button');
      go.type = 'button';
      go.className = 'go';
      go.textContent = 'Go';
      go.disabled = far || m.steps === 0;
      if (far) go.title = 'The map has no way in yet — walk in once and it learns it';
      go.onclick = () => {
        // The same walk as typing it: the whole way at once, shown in the
        // Bot panel.  Options closes so you can see where you are going.
        if (window.sendCommand) window.sendCommand(`/go ${m.name}`);
        if (window.options) window.options.close();
      };
      top.append(name, kind, dist, go);
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = m.note || '';
      row.append(top, meta);
      list.append(row);
    }
    if (window.options) window.options.count('marks', marks.length);
  }

  window.renderMarks = render;

  window.handleMarks = function (m) {
    if (m.op !== 'list') return;
    marks = m.marks || [];
    lost = !!m.lost;
    const can = marks.filter((x) => x.steps != null).length;
    $('marks-now').textContent = m.error ? m.error
      : lost ? 'The map does not know where you are, so there are no distances yet — '
        + 'walk a room, then Update distances.'
        : `How far each is from where you are now. ${can} of ${marks.length} `
          + 'can be reached. For the rest the map has no way in yet — walking in '
          + 'once teaches it.';
    render();
  };

  $('marks-refresh').onclick = window.refreshMarks;
})();
