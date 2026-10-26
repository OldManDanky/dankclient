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
    if (Array.isArray(value)) return [value.join(', '), !value.length];
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

  function rows(body) {
    const box = $('guild-rows');
    box.replaceChildren();
    // A field that is some other field's ceiling is shown beside it, not
    // again on a line of its own.
    const paired = new Set(Object.keys(body)
      .filter((k) => k.endsWith('_max') && body[k.slice(0, -4)] !== undefined));
    const keys = Object.keys(body)
      .filter((k) => !PLUMBING.has(k) && !paired.has(k))
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

  function tabs(names) {
    const strip = $('guild-tabs');
    strip.replaceChildren();
    for (const name of names) {
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(name === chosen));
      // "Guild.Systems" is "Systems" here: the panel is already Guild.
      b.textContent = name.replace(/^Guild\./, '');
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
    rows(data[chosen]);
  }

  window.renderGuilds = render;
})();
