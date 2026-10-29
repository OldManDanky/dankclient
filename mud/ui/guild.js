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
    if (key === 'pct' || key.endsWith('_pct')) return [`${n}%`, n === 0];
    if (key === 'secs' || key.endsWith('_secs')) return [duration(n), n === 0];
    if (key.endsWith('_on')) return [n ? 'on' : 'off', !n];
    const ceiling = body[`${key}_max`];
    if (ceiling !== undefined && Number.isFinite(Number(ceiling))) {
      return [`${group(n)} / ${group(Number(ceiling))}`, false];
    }
    return [group(n), n === 0];
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

  function drawGrid(g, body) {
    const box = $('guild-map');
    if (!box) return;
    box.replaceChildren();
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

    const art = document.createElement('pre');
    art.className = 'gmap';
    art.textContent = g.rows.map((row, y) => {
      if (y !== g.y || g.x === null || g.x < 0 || g.x >= row.length) return row;
      return row.slice(0, g.x) + MARKER + row.slice(g.x + 1);
    }).join('\n');
    box.append(head, art);

    if (g.legend) {
      const key = document.createElement('div');
      key.className = 'gmap-legend';
      // The key is not always keyed by the character on the map: one guild
      // numbers its kinds of ground 0 to 20 and the rows say which is
      // which some other way.  Where the key IS by character, only what is
      // on screen is listed -- a key to a whole world beside a corner of
      // it is a wall of text.  Where it is not, it is listed whole, since
      // there is nothing to match it against.
      // Decided on evidence rather than on the look of the keys: single
      // digits are both plausible glyphs and plausible numbers, so the
      // question is whether any key is actually ON the map.
      const seen = new Set(g.rows.join(''));
      const byGlyph = Object.keys(g.legend)
        .some((k) => k.length === 1 && seen.has(k));
      for (const [glyph, what] of Object.entries(g.legend)) {
        if (byGlyph && !seen.has(glyph)) continue;
        const one = document.createElement('span');
        one.textContent = `${glyph} ${what}`;
        key.append(one);
      }
      if (key.children.length) box.append(key);
    }
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
      return `${group(Number(value.cur) || 0)} / ${group(Number(value.max) || 0)}`;
    }
    if (keys.length === 2 && keys[0] === 'x' && keys[1] === 'y') {
      return `${value.x},${value.y}`;
    }
    return null;
  }

  /* One key and its value, as a pair of cells in whichever grid it is
     going into.  Pulled out of `rows` so a nested record draws the same
     way its parent does, suffix conventions and all. */
  function pair(box, key, body) {
    const [text, off] = show(key, body[key], body);
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
    const paired = new Set(Object.keys(body)
      .filter((k) => k.endsWith('_max') && body[k.slice(0, -4)] !== undefined));
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
    const paired = new Set(cols.filter(
      (k) => k.endsWith('_max') && cols.includes(k.slice(0, -4))));
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
      const k = document.createElement('div');
      k.className = 'k';
      k.textContent = label(key);
      const v = document.createElement('div');
      v.className = 'v';
      v.textContent = inOne;
      box.append(k, v);
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

  function rows(body, drawn) {
    const box = $('guild-rows');
    box.replaceChildren();
    // What the drawing above already says is not said again as rows of
    // glyph strings underneath it.
    const keys = fieldsOf(body, drawn ? GRID_KEYS : []);
    for (const key of keys) draw(box, key, body, 0);
    if (!keys.length) {
      const none = document.createElement('div');
      none.className = 'wide';
      none.textContent = 'nothing in this one yet';
      box.append(none);
    }
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
      pick.setAttribute('aria-label', 'Which guild package to show');
      for (const name of names) {
        const o = document.createElement('option');
        o.value = name;
        o.textContent = shortName(name);
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
      b.textContent = shortName(name);
      b.onclick = () => {
        chosen = name;
        render(data, true);
      };
      strip.append(b);
    }
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
      return;
    }
    if (!keep && !names.includes(chosen)) chosen = names[0];
    if (!names.includes(chosen)) chosen = names[0];
    const who = data[chosen].guild || '';
    $('guild-name').textContent = who;
    tabs(names);
    const g = grid(data[chosen]);
    drawGrid(g, data[chosen]);
    rows(data[chosen], !!g && !g.unreadable);
  }

  window.renderGuilds = render;
})();
