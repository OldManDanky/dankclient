/* The Guild panel: 3Scapes' Guild.* packages, one tab each.

   The field names belong to the guild, not to the client -- a gentech has
   `hypergen_secs` and `tacshield_type`, and the next guild has neither --
   so nothing here knows what any of them mean, and nothing invents a
   friendlier name that might be a lie.  They are the names the player
   already reads in the game.

   What CAN be read without knowing the guild is the shape of a name, and
   the suffixes are a convention the whole feed keeps: `_pct` is a
   percentage, `_secs` is a duration, `_max` is the ceiling of the field it
   is named after, `_on` is a switch.  That is enough to lay the numbers out
   properly for a guild nobody here has ever seen. */

(function () {
  const $ = (id) => document.getElementById(id);
  const PLUMBING = new Set(['guild', 'full', 'page', 'pages']);

  let data = {};
  let chosen = '';

  /* Two things decide whether the panel is on screen: whether the MUD has
     sent any of it (Three Kingdoms never does) and whether it is ticked
     under Options -> Layout.  Panels owns the tick; this reads it, so the
     two do not take turns overruling each other. */
  function wanted() {
    const saved = window.prefs
      ? window.prefs.get('panel:guildpanel:shown', null) : null;
    return saved === null ? true : saved === '1';
  }

  const label = (name) => name.replace(/_/g, ' ');

  /* Grouped from a thousand up, the ordinary rule.  These sit in a
     right-aligned tabular column, so one row grouping and the next not is
     the thing that reads badly. */
  function group(n) {
    return Math.abs(n) >= 1000 ? n.toLocaleString('en-GB') : String(n);
  }

  function duration(secs) {
    const s = Math.max(0, Math.floor(secs));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d) return `${d}d ${h}h`;
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m ${s % 60}s`;
    return `${s}s`;
  }

  /* One field, as a value and whether it is "off" (dimmed). */
  function show(key, value, body) {
    // A list of objects joins to "[object Object]" if you leave it to the
    // default, which is a bug waiting on the first guild that sends one --
    // we have watched exactly one guild's feed, and it sends lists of words.
    if (Array.isArray(value)) {
      const parts = value.map((v) => {
        if (v === null || v === undefined) return '';
        return typeof v === 'object' ? JSON.stringify(v) : String(v);
      });
      return [parts.join(', '), !value.length];
    }
    if (value === null || value === undefined) return ['', true];
    if (typeof value === 'object') return [JSON.stringify(value), false];
    if (typeof value === 'string') return [value, !value.trim()];

    const n = Number(value);
    if (!Number.isFinite(n)) return [String(value), false];
    // Suffixed inside a package (`g2n_pct`, `edna_secs`) and bare inside a
    // record (`wstock[].pct`, `ships[].secs`): both are the live feed.
    // A change since last time reads as one: +3 is a gain, 3 is a total.
    if (key.endsWith('_delta')) return [n > 0 ? `+${group(n)}` : group(n), n === 0];
    if (key === 'pct' || key.endsWith('_pct')) return [`${n}%`, n === 0];
    if (key === 'secs' || key.endsWith('_secs')) return [duration(n), n === 0];
    if (key.endsWith('_on')) return [n ? 'on' : 'off', !n];
    const ceiling = ceilingOf(body, key);
    if (ceiling !== undefined) {
      const [text, pct] = ratio(n, ceiling);
      return [text, false, pct];
    }
    return [group(n), n === 0];
  }

  /* A number against its ceiling.  The percentage is spelled out as well
     as drawn, because "9,393 / 12,000" is two numbers to divide in your
     head and the whole point of a panel is not having to.

     Deliberately not coloured good or bad: a pool you want full and a
     poison you want empty are the same shape, and nothing in the feed
     says which this is.  The bar shows how full, and says nothing about
     whether full is good. */
  function ratio(cur, max) {
    if (!(max > 0)) return [group(cur), null];
    const pct = Math.floor((cur * 100) / max);
    return [`${group(cur)} / ${group(max)}  ${pct}%`, pct];
  }

  /* A package carrying a grid is drawn as one.  Recognised by its SHAPE,
     never by its name: one guild's world map and its battle board both
     arrive as w, h and rows of glyphs, and a third guild we have never
     seen can do the same and get the same drawing for free.

     The rows never contain you -- you are drawn at `pos`, and a `pos` of
     -1,-1 means you are not on this map at all, which is the ordinary
     case for a world map you are not standing on.  `enc` names each
     plane's encoding and is read rather than assumed, so one we cannot
     draw says so instead of drawing nonsense.

     There is deliberately NO test of `active` here.  The help page says a
     battle board is "sent even with no battle, so active: 0 clears a
     panel", and reading that as a rule for every grid was wrong: a live
     world map arrives with `active: 0` and seventy columns of real
     ground, because there `active` is about whether you are on it.  The
     board that has nothing on it sends `terrain: []`, and emptiness is
     the honest test -- it needs no flag and cannot be misread. */
  const GRID_KEYS = ['terrain', 'east', 'south', 'legend', 'enc',
                     'w', 'h', 'pos'];
  const MARKER = '@';

  function grid(body) {
    const rows = body.terrain;
    if (!Array.isArray(rows) || !rows.length) return null;
    if (!rows.every((r) => typeof r === 'string')) return null;
    const enc = body.enc && typeof body.enc === 'object' ? body.enc : {};
    if (enc.terrain && enc.terrain !== 'glyph') {
      return { unreadable: String(enc.terrain) };
    }
    const at = body.pos && typeof body.pos === 'object' ? body.pos : {};
    const x = Number(at.x);
    const y = Number(at.y);
    // -1,-1 is "you are not on this map", not a corner of it.
    const on = Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0;
    return {
      rows,
      x: on ? x : null,
      y: on ? y : null,
      legend: body.legend && typeof body.legend === 'object' && !Array.isArray(body.legend)
        ? body.legend : null,
    };
  }

  //: The popped-out window, while there is one.
  let loose = null;
  let lastMap = null;

  function shut() {
    if (loose && !loose.closed) loose.close();
    loose = null;
    render(data, true);
  }

  /* The window is written once and then redrawn in place.  Its own
     colours are copied off this page rather than linked, so it matches
     whichever theme is in use and keeps matching if the file moves. */
  function popOut() {
    loose = window.open('', 'guildmap',
      'width=760,height=620,menubar=no,toolbar=no');
    if (!loose) return;                 // blocked: the inline map stands
    const style = 'body{margin:0;padding:10px;background:#111;color:#ddd;'
      + 'font-family:monospace}'
      + 'pre{margin:0;line-height:1.05;white-space:pre}'
      + '#h{opacity:.7;font-size:.9em;margin-bottom:6px}'
      + '#k{opacity:.7;font-size:.85em;margin-top:8px;display:flex;'
      + 'flex-wrap:wrap;gap:2px 14px}';
    loose.document.write('<!doctype html><meta charset="utf-8">'
      + '<title>Guild map</title><style>' + style + '</style>'
      + '<div id="h"></div><pre id="m"></pre><div id="k"></div>');
    loose.document.close();
    // Closing it from its own title bar puts the map back in the panel.
    loose.addEventListener('unload', () => {
      loose = null;
      setTimeout(() => render(data, true), 0);
    });
    render(data, true);
  }

  function paintLoose(g, body) {
    if (!loose || loose.closed) return;
    const d = loose.document;
    const h = d.getElementById('h');
    const m = d.getElementById('m');
    const k = d.getElementById('k');
    if (!h || !m || !k) return;
    const size = `${Number(body.w) || g.rows[0].length}`
      + `\u00d7${Number(body.h) || g.rows.length}`;
    h.textContent = g.x === null ? size : `${size} — you are at ${g.x},${g.y}`;
    m.textContent = marked(g);
    k.replaceChildren();
    for (const [glyph, what] of legendOf(g)) {
      const one = d.createElement('span');
      one.textContent = `${glyph} ${what}`;
      k.append(one);
    }
  }

  //: The rows with you put in at `pos`, which they never contain.
  function marked(g) {
    return g.rows.map((row, y) => {
      if (y !== g.y || g.x === null || g.x < 0 || g.x >= row.length) return row;
      return row.slice(0, g.x) + MARKER + row.slice(g.x + 1);
    }).join('\n');
  }

  /* The key, as pairs.  Not always keyed by the character on the map: one
     guild numbers its kinds of ground and the rows use letters.  Decided
     on evidence rather than on the look of the keys -- whether any key is
     actually ON the map -- because a single digit is both a plausible
     glyph and a plausible number.  Where it is by character, only what is
     on screen is listed; where it is not, there is nothing to match
     against, so it is listed whole. */
  function legendOf(g) {
    if (!g.legend) return [];
    const seen = new Set(g.rows.join(''));
    const byGlyph = Object.keys(g.legend)
      .some((k) => k.length === 1 && seen.has(k));
    return Object.entries(g.legend)
      .filter(([glyph]) => !byGlyph || seen.has(glyph));
  }

  function drawGrid(g, body) {
    const box = $('guild-map');
    if (!box) return;
    box.replaceChildren();
    lastMap = g && !g.unreadable ? { g, body } : null;
    if (lastMap) paintLoose(g, body);
    if (!g) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    if (g.unreadable) {
      const say = document.createElement('p');
      say.className = 'fhint';
      // Honest rather than wrong: we would be drawing the bytes of some
      // other encoding as though they were characters.
      say.textContent = `The map is sent as ${g.unreadable}, which this `
        + 'panel cannot draw yet.';
      box.append(say);
      return;
    }
    const head = document.createElement('div');
    head.className = 'gmap-head';
    const size = `${Number(body.w) || g.rows[0].length}`
      + `\u00d7${Number(body.h) || g.rows.length}`;
    head.textContent = g.x === null ? size : `${size} — you are at ${g.x},${g.y}`;

    /* Out into a window of its own.  A world seventy columns across does
       not belong in a sidebar, and in app mode a new window is the
       client's own -- same page, same feed, so it is drawn into from here
       rather than being a second client. */
    const out = document.createElement('button');
    out.type = 'button';
    out.className = 'gmap-out';
    out.textContent = loose && !loose.closed ? 'bring back' : 'pop out';
    out.onclick = () => (loose && !loose.closed ? shut() : popOut());
    head.append(out);

    const art = document.createElement('pre');
    art.className = 'gmap';
    art.textContent = marked(g);
    box.append(head, art);
    // While it is out in its own window the panel keeps the heading --
    // and its button to bring it back -- but not a second copy of a map.
    if (loose && !loose.closed) {
      art.remove();
      return;
    }

    const key = document.createElement('div');
    key.className = 'gmap-legend';
    for (const [glyph, what] of legendOf(g)) {
      const one = document.createElement('span');
      one.textContent = `${glyph} ${what}`;
      key.append(one);
    }
    if (key.children.length) box.append(key);
  }

  const isRecord = (v) => !!v && typeof v === 'object' && !Array.isArray(v);

  /* A list of records -- ships, stock, routes, a roster -- is a table.
     Written out as one value per line it is the raw feed with commas in
     it, which is exactly what nobody wants to read. */
  const isTable = (v) => Array.isArray(v) && v.length
    && v.every((e) => isRecord(e));

  //: Rows of a table before it is cut short, and the widest a table gets
  //: before it scrolls on its own rather than widening the sidebar.
  const ROWS = 20;

  /* Some small records read better on one line than as a group of their
     own: a current and a ceiling is the pair we already draw everywhere
     else, and a coordinate is two numbers with a comma. */
  function inline(value) {
    const keys = Object.keys(value).sort();
    if (keys.length === 2 && keys[0] === 'cur' && keys[1] === 'max') {
      return ratio(Number(value.cur) || 0, Number(value.max) || 0);
    }
    if (keys.length === 2 && keys[0] === 'x' && keys[1] === 'y') {
      return [`${value.x},${value.y}`, null];
    }
    return null;
  }

  /* One key and its value, as a pair of cells in whichever grid it is
     going into.  Pulled out of `rows` so a nested record draws the same
     way its parent does, suffix conventions and all. */
  function cell(box, key, text, off, pct) {
    const k = document.createElement('div');
    k.className = 'k';
    k.textContent = label(key);
    const v = document.createElement('div');
    v.className = 'v' + (off ? ' off' : '');
    v.textContent = text;
    // A long value reads better across the whole panel than squeezed into
    // the value column.
    if (text.length > 28) {
      k.className = 'k wide';
      v.className = 'wide' + (off ? ' off' : '');
    }
    box.append(k, v);
    if (pct !== null && pct !== undefined) {
      const bar = document.createElement('div');
      bar.className = 'gbar';
      // Over its own ceiling is drawn full rather than overflowing; the
      // numbers beside it still say what really happened.
      bar.style.setProperty('--fill', `${Math.max(0, Math.min(100, pct))}%`);
      box.append(bar);
    }
  }

  function pair(box, key, body) {
    const [text, off, pct] = show(key, body[key], body);
    cell(box, key, text, off, pct);
  }

  function heading(box, key) {
    const h = document.createElement('div');
    h.className = 'ghead';
    h.textContent = label(key);
    box.append(h);
    return h;
  }

  /* The keys of a record, minus the ceilings drawn beside their own
     field, and minus the plumbing. */
  function fieldsOf(body, skip) {
    const paired = ceilings(body);
    return Object.keys(body)
      .filter((k) => !PLUMBING.has(k) && !paired.has(k)
                     && !(skip || []).includes(k))
      .sort();
  }

  function drawTable(box, key, list) {
    heading(box, key);
    const wrap = document.createElement('div');
    wrap.className = 'gtable';
    const table = document.createElement('table');

    // Columns in the order the first record names them, then anything a
    // later one adds -- the MUD's own order says more than alphabetical.
    const cols = [];
    for (const rec of list) {
      for (const k of Object.keys(rec)) if (!cols.includes(k)) cols.push(k);
    }
    // Same two conventions as a row, judged on the first record that has
    // the pair: a column is a ceiling or it is not, the whole way down.
    const sample = list.find((r) => ceilings(r).size) || list[0];
    const paired = ceilings(sample);
    /* A column appears when it has something to say.  Blank or zero the
       whole way down it says nothing you could act on -- the fleet sends
       thirteen fields per ship and five of them are zero for every ship
       you own -- and the absence is itself the answer: the column turns
       up the day a ship is held or has a crew.  This is a list view and
       applies only here; a lone record still shows its zeros, because
       there "0 / 0" is the reading. */
    const empty = (v) => v === '' || v === null || v === undefined
      || v === 0 || (Array.isArray(v) && !v.length);
    const keep = cols.filter((k) => !paired.has(k) && !PLUMBING.has(k)
      && list.some((rec) => !empty(rec[k])));

    const head = document.createElement('tr');
    for (const k of keep) {
      const th = document.createElement('th');
      th.textContent = label(k);
      head.append(th);
    }
    table.append(head);

    for (const rec of list.slice(0, ROWS)) {
      const tr = document.createElement('tr');
      for (const k of keep) {
        const td = document.createElement('td');
        const [text, off] = show(k, rec[k], rec);
        td.textContent = text;
        if (off) td.className = 'off';
        tr.append(td);
      }
      table.append(tr);
    }
    wrap.append(table);
    box.append(wrap);

    if (list.length > ROWS) {
      const rest = document.createElement('div');
      rest.className = 'wide off';
      rest.textContent = `... and ${list.length - ROWS} more`;
      box.append(rest);
    }
  }

  function drawRecord(box, key, rec) {
    const inOne = inline(rec);
    if (inOne !== null) {
      cell(box, key, inOne[0], false, inOne[1]);
      return;
    }
    const keys = fieldsOf(rec);
    if (!keys.length) return;        // an empty record says nothing
    heading(box, key);
    const sub = document.createElement('div');
    sub.className = 'gsub';
    for (const k of keys) draw(sub, k, rec, 1);
    box.append(sub);
  }

  /* One field, wherever it sits.  Depth is capped: a record inside a
     record inside a record is drawn as its text rather than nested
     forever, which keeps a surprise in the feed from running away with
     the panel. */
  function draw(box, key, body, depth) {
    const value = body[key];
    if (isTable(value) && depth < 2) {
      drawTable(box, key, value);
    } else if (isRecord(value) && depth < 2) {
      drawRecord(box, key, value);
    } else {
      pair(box, key, body);
    }
  }

  /* Where a field's ceiling lives.  Two conventions, both off the same
     live feed and both in the same package: `pu` with `pu_max`, and
     `fury` with `mfury`.  The second is only believed when the field it
     would pair with actually exists beside it and both are numbers --
     otherwise `mode` would pair itself with an `ode` that is not there. */
  function ceilingOf(body, key) {
    for (const name of [`${key}_max`, `m${key}`]) {
      const v = body[name];
      if (v !== undefined && v !== null && v !== ''
          && Number.isFinite(Number(v))) return Number(v);
    }
    return undefined;
  }

  //: The keys that are some other key's ceiling, and so are not rows.
  function ceilings(body) {
    const has = (k) => Object.prototype.hasOwnProperty.call(body, k);
    return new Set(Object.keys(body).filter((k) => {
      if (k.endsWith('_max') && has(k.slice(0, -4))) {
        return ceilingOf(body, k.slice(0, -4)) !== undefined;
      }
      if (k.length > 1 && k.startsWith('m') && has(k.slice(1))) {
        return Number.isFinite(Number(body[k]))
          && Number.isFinite(Number(body[k.slice(1)]));
      }
      return false;
    }));
  }

  function rows(tab, mapped) {
    const box = $('guild-rows');
    box.replaceChildren();
    for (const name of tab.packages) {
      // Only where a tab gathers several: one package on a tab of its
      // own is already named by the tab.
      if (tab.packages.length > 1) {
        const h = document.createElement('div');
        h.className = 'gpack';
        h.textContent = shortName(name);
        box.append(h);
      }
      fields(box, data[name], name === mapped);
    }
    if (!box.children.length) {
      const none = document.createElement('div');
      none.className = 'wide';
      none.textContent = 'nothing in this one yet';
      box.append(none);
    }
  }

  function fields(box, body, drawn) {
    // What the drawing above already says is not said again as rows of
    // glyph strings underneath it.
    const keys = fieldsOf(body, drawn ? GRID_KEYS : []);
    /* Plain values first, then the blocks, then the tables.  Sorted
       together, one alphabetical stream, a forty-row table lands between
       two numbers and pushes everything you came to read off the bottom.
       The other client arranges each guild's page by hand; this is the
       part of that worth having without knowing a thing about the guild
       -- the small facts where the eye lands, the bulk underneath. */
    const kind = (key) => {
      const v = body[key];
      if (isTable(v)) return 2;
      if (isRecord(v) && inline(v) === null) return 1;
      return 0;
    };
    for (const key of [...keys].sort((a, b) => kind(a) - kind(b)))
      draw(box, key, body, 0);
  }

  // "Guild.Systems" is "Systems" here: the panel is already Guild.
  const shortName = (name) => name.replace(/^Guild\./, '');

  /* A tab per package up to a point.  One guild sends seven, which wraps to
     two rows and reads at a glance; others send sixteen, and sixteen wrapped
     buttons fill the panel before a single number shows.  Past this many it
     becomes one dropdown instead -- a click to see what else is there, in
     exchange for the space the numbers are the point of. */
  const MANY = 8;

  function tabs(names) {
    const strip = $('guild-tabs');
    strip.replaceChildren();
    if (names.length > MANY) {
      const pick = document.createElement('select');
      pick.setAttribute('aria-label', 'Which part of the guild to show');
      for (const name of names) {
        const o = document.createElement('option');
        o.value = name;
        o.textContent = name;
        pick.append(o);
      }
      pick.value = chosen;
      pick.onchange = () => {
        chosen = pick.value;
        render(data, true);
      };
      strip.append(pick);
      return;
    }
    for (const name of names) {
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(name === chosen));
      b.textContent = name;
      b.onclick = () => {
        chosen = name;
        render(data, true);
      };
      strip.append(b);
    }
  }

  /* The tabs, as this guild's layout groups them -- or one per package
     where there is no layout for it.  Either way a tab is a title and the
     packages under it, so everything downstream is one shape. */
  function grouped(names) {
    const first = data[names[0]] || {};
    const who = String(first.guild || '').toLowerCase();
    const plan = (window.GUILD_LAYOUTS || {})[who];
    if (!plan) return names.map((n) => ({ title: shortName(n), packages: [n] }));

    const out = [];
    const taken = new Set();
    for (const tab of plan) {
      const has = tab.packages.filter((n) => names.includes(n));
      if (!has.length) continue;          // none of this one's arrived
      has.forEach((n) => taken.add(n));
      out.push({ title: tab.title, packages: has });
    }
    /* Whatever the layout does not mention.  The point of this tab is
       that a layout cannot lose anything: a package the guild starts
       sending tomorrow turns up here on its own. */
    const rest = names.filter((n) => !taken.has(n));
    if (rest.length) out.push({ title: 'Other', packages: rest });
    return out;
  }

  function render(next, keep) {
    // Called with nothing when only the tick changed: keep what we have.
    if (next !== undefined) data = next || {};
    const names = Object.keys(data).sort();
    const panel = $('guildpanel');
    if (!panel) return;
    panel.hidden = !names.length || !wanted();
    if (!names.length) {
      chosen = '';
      drawGrid(null);
      return;
    }
    const plan = grouped(names);
    const titles = plan.map((t) => t.title);
    if (!titles.includes(chosen)) chosen = titles[0];
    const tab = plan.find((t) => t.title === chosen);
    $('guild-name').textContent = data[tab.packages[0]].guild || '';
    tabs(titles);

    // A tab may hold more than one package, so the map is whichever of
    // them carries a grid -- in practice the one a layout has put alone
    // on a tab of its own.
    const mapped = tab.packages.find((n) => grid(data[n]));
    const g = mapped ? grid(data[mapped]) : null;
    drawGrid(g, mapped ? data[mapped] : {});
    rows(tab, mapped);
  }

  window.renderGuilds = render;
})();
