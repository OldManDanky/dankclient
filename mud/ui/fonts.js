/* Options -> Fonts: the terminal's font, its size and line spacing, and the
   size of the messages window.

   Kept in the browser, like Panels: which fonts exist is a fact about this
   computer, not about the character.

   A page cannot ask the computer for its list of fonts without a permission
   prompt, but it can ask whether one particular font is there -- text drawn
   in it comes out a different width from the fallbacks -- so the list is the
   fixed-width fonts people actually have, trimmed to the installed ones, with
   Other for anything else.  Fixed-width because the terminal is a grid: 3K's
   maps and tables are drawn in columns, and a font whose letters are
   different widths draws them crooked. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;

  const DEFAULTS = { family: '', size: 14, line: 1, msg: 11 };
  const KNOWN = [
    'Consolas', 'Cascadia Mono', 'Cascadia Code', 'Lucida Console',
    'Courier New', 'JetBrains Mono', 'Fira Code', 'Fira Mono',
    'Source Code Pro', 'IBM Plex Mono', 'Hack', 'Inconsolata', 'Ubuntu Mono',
    'DejaVu Sans Mono', 'Liberation Mono', 'Noto Sans Mono', 'Menlo', 'Monaco',
  ];
  const SIZES = [10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24];
  const LINES = [1, 1.1, 1.2, 1.3, 1.4, 1.5];
  const MSG_SIZES = [9, 10, 11, 12, 13, 14, 16];
  const OTHER = '__other__';        // the "Other..." entry; no font is called this

  if (!$('font-family')) return;

  // --- asking about a font ---------------------------------------------------

  const pen = document.createElement('canvas').getContext('2d');

  function width(font, text) {
    pen.font = font;
    return pen.measureText(text).width;
  }

  /* Drawn in it, text differs in width from at least one fallback, which it
     would not if the name fell through to that fallback. */
  function installed(name) {
    const text = 'mmmmmmmmmmlli10OO@#';
    return ['monospace', 'serif', 'sans-serif'].some((base) =>
      width(`40px ${base}`, text) !== width(`40px "${name}", ${base}`, text));
  }

  function fixedWidth(name) {
    const font = `40px "${name}", monospace`;
    return Math.abs(width(font, 'iiiiiiiiii') - width(font, 'MMMMMMMMMM')) < 0.5;
  }

  // --- the choice ------------------------------------------------------------

  function read() {
    const num = (key, fallback, parse) => parse(store.get(key, String(fallback))) || fallback;
    return {
      family: store.get('font:family', DEFAULTS.family),
      size: num('font:size', DEFAULTS.size, (v) => parseInt(v, 10)),
      line: num('font:line', DEFAULTS.line, parseFloat),
      msg: num('font:msg', DEFAULTS.msg, (v) => parseInt(v, 10)),
    };
  }

  function save(c) {
    store.set('font:family', c.family);
    store.set('font:size', String(c.size));
    store.set('font:line', String(c.line));
    store.set('font:msg', String(c.msg));
  }

  function apply(c) {
    const stack = window.fontStack ? window.fontStack(c.family) : 'monospace';
    const root = document.documentElement.style;
    root.setProperty('--term-font', stack);
    root.setProperty('--term-size', `${c.size}px`);
    root.setProperty('--cm-size', `${c.msg}px`);
    if (window.setTerminalFont) window.setTerminalFont(c.family, c.size, c.line);
    const preview = $('font-preview');
    preview.style.fontSize = `${c.size}px`;
    preview.style.lineHeight = String(c.line);
  }

  function change(part) {
    const c = Object.assign(read(), part);
    save(c);
    apply(c);
  }

  // --- the controls ----------------------------------------------------------

  function options(select, values, label, chosen) {
    select.replaceChildren();
    for (const v of values) {
      const o = document.createElement('option');
      o.value = String(v);
      o.textContent = label(v);
      select.append(o);
    }
    select.value = String(chosen);
  }

  function fill() {
    const c = read();
    const found = KNOWN.filter(installed);
    const families = [''].concat(found);
    if (c.family && !families.includes(c.family)) families.push(c.family);
    families.push(OTHER);
    options($('font-family'), families, (f) => (f === '' ? 'Default (Consolas)'
      : f === OTHER ? 'Other\u2026' : f), c.family);
    options($('font-size'), SIZES, (s) => `${s} px`, c.size);
    options($('font-line'), LINES, (l) => (l === 1 ? 'single' : `${l}\u00d7`), c.line);
    options($('font-msg'), MSG_SIZES, (s) => `${s} px`, c.msg);
    $('font-other-row').hidden = true;
  }

  $('font-family').onchange = () => {
    const v = $('font-family').value;
    if (v === OTHER) {
      $('font-other-row').hidden = false;
      $('font-other').value = '';
      $('font-other').focus();
      return;
    }
    $('font-other-row').hidden = true;
    change({ family: v });
  };

  $('font-other').onkeydown = (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const name = $('font-other').value.replace(/["\\;{}]/g, '').trim();
    const hint = $('font-other-hint');
    hint.classList.remove('warn');
    if (!name) return;
    if (!installed(name)) {
      hint.textContent = `\u201c${name}\u201d is not installed on this computer.`;
      hint.classList.add('warn');
      return;
    }
    if (!fixedWidth(name)) {
      hint.textContent = `\u201c${name}\u201d is not fixed-width, so maps and tables `
        + 'will not line up. Using it anyway.';
      hint.classList.add('warn');
    } else {
      hint.textContent = 'Type its name and press Enter.';
    }
    change({ family: name });
    fill();
    $('font-other-row').hidden = hint.classList.contains('warn') ? false : true;
  };

  $('font-size').onchange = () => change({ size: parseInt($('font-size').value, 10) });
  $('font-line').onchange = () => change({ line: parseFloat($('font-line').value) });
  $('font-msg').onchange = () => change({ msg: parseInt($('font-msg').value, 10) });

  $('font-reset').onclick = () => {
    save(DEFAULTS);
    fill();
    apply(DEFAULTS);
  };

  fill();
  apply(read());
})();
