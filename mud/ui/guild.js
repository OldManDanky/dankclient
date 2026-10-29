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
    if (key.endsWith('_pct')) return [`${n}%`, n === 0];
    if (key.endsWith('_secs')) return [duration(n), n === 0];
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

     Three rules come from the MUD's own help page rather than from
     guesswork.  The rows never contain you -- you are drawn at `pos`.
     `enc` names each plane's encoding and is to be read rather than
     assumed, so an encoding we cannot draw says so instead of drawing
     nonsense.  And `active: 0` means "nothing here", which is how a board
     with no battle on it clears itself. */
  const GRID_KEYS = ['terrain', 'east', 'south', 'legend', 'enc',
                     'w', 'h', 'pos'];
  const MARKER = '@';

  function grid(body) {
    const rows = body.terrain;
    if (!Array.isArray(rows) || !rows.length) return null;
    if (!rows.every((r) => typeof r === 'string')) return null;
    if (body.active !== undefined && !Number(body.active)) return null;
    const enc = body.enc && typeof body.enc === 'object' ? body.enc : {};
    if (enc.terrain && enc.terrain !== 'glyph') {
      return { unreadable: String(enc.terrain) };
    }
    const at = body.pos && typeof body.pos === 'object' ? body.pos : {};
    const x = Number(at.x);
    const y = Number(at.y);
    return {
      rows,
      x: Number.isFinite(x) ? x : null,
      y: Number.isFinite(y) ? y : null,
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
      const seen = new Set(g.rows.join(''));
      for (const [glyph, what] of Object.entries(g.legend)) {
        // Only what is actually on this map: a legend for the whole world
        // is a wall of text beside a corner of it.
        if (!seen.has(glyph)) continue;
        const one = document.createElement('span');
        one.textContent = `${glyph} ${what}`;
        key.append(one);
      }
      if (key.children.length) box.append(key);
    }
  }

  function rows(body, drawn) {
    const box = $('guild-rows');
    box.replaceChildren();
    // A field that is some other field's ceiling is shown beside it, not
    // again on a line of its own.
    const paired = new Set(Object.keys(body)
      .filter((k) => k.endsWith('_max') && body[k.slice(0, -4)] !== undefined));
    // What the drawing above already says is not said again as rows of
    // glyph strings underneath it.
    const shown = drawn ? GRID_KEYS : [];
    const keys = Object.keys(body)
      .filter((k) => !PLUMBING.has(k) && !paired.has(k) && !shown.includes(k))
      .sort();
    for (const key of keys) {
      const [text, off] = show(key, body[key], body);
      const k = document.createElement('div');
      k.className = 'k';
      k.textContent = label(key);
      const v = document.createElement('div');
      v.className = 'v' + (off ? ' off' : '');
      v.textContent = text;
      // A long list reads better across the whole panel than squeezed into
      // the value column.
      if (text.length > 28) {
        k.className = 'k wide';
        v.className = 'wide' + (off ? ' off' : '');
      }
      box.append(k, v);
    }
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
