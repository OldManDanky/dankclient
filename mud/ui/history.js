/* Your commands.  ↑ and ↓ walk back through them in the box; History -- the
   button at the end of the box, or Ctrl+↑ -- lists them to search and pick
   from.  Picking one puts it in the box and sends nothing: it is there to be
   changed, or sent with Enter.

   Kept in this browser, the last 500, so a reload does not forget them.  Only
   what is typed once MIP is live is saved: before that, the box may be
   answering 3K's own login prompt, password and all. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;
  const KEY = 'cmd:history';
  const MOST = 500;
  //: the most rows drawn at once; a search finds the rest
  const SHOWN = 200;

  function read() {
    try {
      const got = JSON.parse(store.get(KEY, '[]'));
      return Array.isArray(got)
        ? got.filter((x) => typeof x === 'string' && x).slice(-MOST) : [];
    } catch (err) {
      return [];                       // a bad preference is no preference
    }
  }

  //: oldest first, the way ↑ walks it
  const lines = read();
  //: the part of it that is saved
  const kept = lines.slice();

  function add(text, keep) {
    if (!text) return;
    // One entry for a command sent ten times running, not ten.
    if (lines[lines.length - 1] !== text) {
      lines.push(text);
      if (lines.length > MOST) lines.shift();
    }
    if (keep && kept[kept.length - 1] !== text) {
      kept.push(text);
      if (kept.length > MOST) kept.shift();
      store.set(KEY, JSON.stringify(kept));
    }
  }

  /* Newest first, each command once, holding every word searched for. */
  function matching(query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const seen = new Set();
    const out = [];
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      if (seen.has(line)) continue;
      seen.add(line);
      const low = line.toLowerCase();
      if (words.every((w) => low.includes(w))) out.push(line);
    }
    return out;
  }

  const box = $('hist');
  const find = $('hist-find');
  const list = $('hist-list');
  const cmd = $('cmd');
  const button = $('hist-open');
  if (!box || !find || !list || !cmd) return;

  let rows = [];
  let picked = 0;

  function draw() {
    const query = find.value.trim();
    rows = matching(query).slice(0, SHOWN);
    picked = Math.max(0, Math.min(picked, rows.length - 1));
    list.replaceChildren();
    if (!rows.length) {
      const none = document.createElement('p');
      none.className = 'hist-none';
      none.textContent = !lines.length ? 'Nothing typed yet.'
        : `Nothing you have typed has “${query}” in it.`;
      list.append(none);
      return;
    }
    rows.forEach((line, i) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'hist-row' + (i === picked ? ' on' : '');
      row.textContent = line;
      row.title = 'Put it in the command box';
      // Keeps the keyboard in the search box until the click has landed.
      row.onmousedown = (e) => e.preventDefault();
      row.onclick = () => take(line);
      list.append(row);
      if (i === picked && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
    });
  }

  function show() {
    // Just above the command box, wherever that is today: the vitals strip
    // can sit over it or under it.
    const bar = $('bar');
    const host = box.parentElement;
    if (bar && host && host.getBoundingClientRect) {
      const gap = host.getBoundingClientRect().bottom - bar.getBoundingClientRect().top;
      box.style.bottom = `${Math.round(gap + 4)}px`;
    }
    box.hidden = false;
    find.value = '';
    picked = 0;
    draw();
    find.focus();
  }

  function hide() {
    box.hidden = true;
    cmd.focus();
  }

  function take(line) {
    cmd.value = line;
    hide();
    if (cmd.setSelectionRange) cmd.setSelectionRange(line.length, line.length);
  }

  find.oninput = () => {
    picked = 0;
    draw();
  };
  find.onkeydown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      hide();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      picked += e.key === 'ArrowDown' ? 1 : -1;
      draw();
    } else if (e.key === 'Enter') {
      // Not the command box's form: this picks one, it does not send it.
      e.preventDefault();
      if (e.stopPropagation) e.stopPropagation();
      if (rows[picked] !== undefined) take(rows[picked]);
    }
  };
  if (button) button.onclick = () => (box.hidden ? show() : hide());
  document.addEventListener('mousedown', (e) => {
    if (box.hidden) return;
    const t = e.target;
    if (box.contains(t) || (button && button.contains(t))) return;
    box.hidden = true;
  });

  window.cmdHistory = { add, list: () => lines.slice(), open: show, close: hide };
})();
