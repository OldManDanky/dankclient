/* Options -> Colours: the terminal's colour scheme, and the look of
   everything around it.

   Kept in the browser, like Fonts: how a screen looks is about the screen,
   not the character.  Loaded before app.js, so the terminal is made in the
   chosen scheme from the start and the page's colours are set before anything
   is drawn -- rather than the default for a moment, then the choice.

   The built-in schemes are the palettes as their own projects publish them,
   credited below.  Anybody else's comes in from a file: terminalcolors.com and
   most schemes' own sites offer Alacritty (.toml), iTerm2 (.itermcolors),
   Ghostty, Windows Terminal (.json) or Xresources, and all five are read.

   Only the sixteen colours 3K's ANSI codes name are the scheme's.  A client
   cannot recolour what a MUD sends as 256-colour or true colour, and does not
   try. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;

  const BASE = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'];
  const cap = (k) => k[0].toUpperCase() + k.slice(1);
  //: xterm's names, in ANSI order: 0-7 then the bright 8-15
  const ANSI = [...BASE, ...BASE.map((k) => 'bright' + cap(k))];

  function scheme(id, name, by, background, foreground, selection, ansi) {
    const s = { id, name, by, background, foreground, selection };
    ANSI.forEach((k, i) => { s[k] = ansi[i]; });
    s.light = luminance(background) > 0.4;
    return s;
  }

  //: xterm.js's own sixteen -- which are Tango's -- and so what 3K's colours
  //: have always looked like here.
  const TANGO = ['#2e3436', '#cc0000', '#4e9a06', '#c4a000', '#3465a4', '#75507b', '#06989a', '#d3d7cf',
    '#555753', '#ef2929', '#8ae234', '#fce94f', '#729fcf', '#ad7fa8', '#34e2e2', '#eeeeec'];
  const SOLARIZED = ['#073642', '#dc322f', '#859900', '#b58900', '#268bd2', '#d33682', '#2aa198', '#eee8d5',
    '#002b36', '#cb4b16', '#586e75', '#657b83', '#839496', '#6c71c4', '#93a1a1', '#fdf6e3'];

  const SCHEMES = [
    scheme('dank', 'Dank', 'this client', '#111318', '#d8dde6', '', TANGO),
    scheme('tango', 'Linux Tango', 'the Tango Desktop Project', '#2e3436', '#d3d7cf', '', TANGO),
    scheme('solarized-dark', 'Solarized Dark', 'Ethan Schoonover', '#002b36', '#839496', '#073642', SOLARIZED),
    scheme('solarized-light', 'Solarized Light', 'Ethan Schoonover', '#fdf6e3', '#657b83', '#eee8d5', SOLARIZED),
    scheme('dracula', 'Dracula', 'Zeno Rocha', '#282a36', '#f8f8f2', '#44475a',
      ['#21222c', '#ff5555', '#50fa7b', '#f1fa8c', '#bd93f9', '#ff79c6', '#8be9fd', '#f8f8f2',
        '#6272a4', '#ff6e6e', '#69ff94', '#ffffa5', '#d6acff', '#ff92df', '#a4ffff', '#ffffff']),
    scheme('gruvbox-dark', 'Gruvbox Dark', 'Pavel Pertsev', '#282828', '#ebdbb2', '#504945',
      ['#282828', '#cc241d', '#98971a', '#d79921', '#458588', '#b16286', '#689d6a', '#a89984',
        '#928374', '#fb4934', '#b8bb26', '#fabd2f', '#83a598', '#d3869b', '#8ec07c', '#ebdbb2']),
    scheme('nord', 'Nord', 'Arctic Ice Studio', '#2e3440', '#d8dee9', '#434c5e',
      ['#3b4252', '#bf616a', '#a3be8c', '#ebcb8b', '#81a1c1', '#b48ead', '#88c0d0', '#e5e9f0',
        '#4c566a', '#bf616a', '#a3be8c', '#ebcb8b', '#81a1c1', '#b48ead', '#8fbcbb', '#eceff4']),
    // Atom's One Dark as a terminal is Nathan Buchar's port, the one people use.
    scheme('one-dark', 'One Dark', 'Nathan Buchar', '#1e2127', '#abb2bf', '#3e4451',
      ['#1e2127', '#e06c75', '#98c379', '#d19a66', '#61afef', '#c678dd', '#56b6c2', '#abb2bf',
        '#5c6370', '#e06c75', '#98c379', '#d19a66', '#61afef', '#c678dd', '#56b6c2', '#ffffff']),
    scheme('catppuccin-mocha', 'Catppuccin Mocha', 'Catppuccin', '#1e1e2e', '#cdd6f4', '#585b70',
      ['#45475a', '#f38ba8', '#a6e3a1', '#f9e2af', '#89b4fa', '#f5c2e7', '#94e2d5', '#bac2de',
        '#585b70', '#f38ba8', '#a6e3a1', '#f9e2af', '#89b4fa', '#f5c2e7', '#94e2d5', '#a6adc8']),
    scheme('tomorrow-night', 'Tomorrow Night', 'Chris Kempson', '#1d1f21', '#c5c8c6', '#373b41',
      ['#000000', '#cc6666', '#b5bd68', '#f0c674', '#81a2be', '#b294bb', '#8abeb7', '#ffffff',
        '#000000', '#cc6666', '#b5bd68', '#f0c674', '#81a2be', '#b294bb', '#8abeb7', '#ffffff']),
    scheme('rose-pine', 'Rosé Pine', 'Rosé Pine', '#191724', '#e0def4', '#403d52',
      ['#26233a', '#eb6f92', '#31748f', '#f6c177', '#9ccfd8', '#c4a7e7', '#ebbcba', '#e0def4',
        '#6e6a86', '#eb6f92', '#31748f', '#f6c177', '#9ccfd8', '#c4a7e7', '#ebbcba', '#e0def4']),
    scheme('monokai', 'Monokai', 'Wimer Hazenberg', '#272822', '#f8f8f2', '#49483e',
      ['#272822', '#f92672', '#a6e22e', '#f4bf75', '#66d9ef', '#ae81ff', '#a1efe4', '#f8f8f2',
        '#75715e', '#f92672', '#a6e22e', '#f4bf75', '#66d9ef', '#ae81ff', '#a1efe4', '#f9f8f5']),
    scheme('campbell', 'Campbell', 'Windows Terminal', '#0c0c0c', '#cccccc', '',
      ['#0c0c0c', '#c50f1f', '#13a10e', '#c19c00', '#0037da', '#881798', '#3a96dd', '#cccccc',
        '#767676', '#e74856', '#16c60c', '#f9f1a5', '#3b78ff', '#b4009e', '#61d6d6', '#f2f2f2']),
  ];

  // --- colour arithmetic -------------------------------------------------------

  /* "#abc", "abc", "0xaabbcc", '"#AABBCC"' -> "#aabbcc", or "" if it is none. */
  function hex(value) {
    let s = String(value == null ? '' : value).trim().replace(/^["']|["']$/g, '');
    if (/^0x[0-9a-f]{6}$/i.test(s)) s = s.slice(2);
    s = s.replace(/^#/, '');
    if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join('');
    return /^[0-9a-f]{6}$/i.test(s) ? '#' + s.toLowerCase() : '';
  }

  function rgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  /* `t` of the way from one colour to another. */
  function mix(a, b, t) {
    const x = rgb(a);
    const y = rgb(b);
    return '#' + x.map((c, i) => Math.round(c + (y[i] - c) * t).toString(16).padStart(2, '0')).join('');
  }

  function alpha(h, a) {
    const [r, g, b] = rgb(h);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }

  function luminance(h) {
    const [r, g, b] = rgb(h).map((c) => {
      const v = c / 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  // --- reading a scheme from a file ---------------------------------------------

  function parseAlacritty(text) {
    const found = {};
    let section = '';
    for (const raw of text.split(/\r?\n/)) {
      const head = raw.match(/^\s*\[([^\]]+)\]/);
      if (head) {
        section = head[1].trim().toLowerCase();
        continue;
      }
      const kv = raw.match(/^\s*([A-Za-z_]+)\s*=\s*["']?(#?[0-9A-Fa-fx]{3,8})["']?/);
      if (!kv) continue;
      const key = kv[1].toLowerCase();
      const value = hex(kv[2]);
      if (!value) continue;
      if (section === 'colors.primary' && (key === 'background' || key === 'foreground')) found[key] = value;
      else if (section === 'colors.normal' && BASE.includes(key)) found[key] = value;
      else if (section === 'colors.bright' && BASE.includes(key)) found['bright' + cap(key)] = value;
      else if (section === 'colors.cursor' && key === 'cursor') found.cursor = value;
      else if (section === 'colors.selection' && key === 'background') found.selection = value;
    }
    return found;
  }

  function parseITerm(text) {
    const found = {};
    const entry = /<key>([^<]+)<\/key>\s*<dict>([\s\S]*?)<\/dict>/g;
    let m;
    while ((m = entry.exec(text))) {
      const name = m[1].trim();
      const body = m[2];
      const part = (c) => {
        const got = body.match(new RegExp(`<key>${c} Component</key>\\s*<real>([^<]+)</real>`));
        return got ? parseFloat(got[1]) : NaN;
      };
      const parts = [part('Red'), part('Green'), part('Blue')];
      if (parts.some(Number.isNaN)) continue;
      const value = '#' + parts.map((v) => Math.round(Math.max(0, Math.min(1, v)) * 255)
        .toString(16).padStart(2, '0')).join('');
      const ansi = name.match(/^Ansi (\d+) Color$/);
      if (ansi && Number(ansi[1]) < 16) found[ANSI[Number(ansi[1])]] = value;
      else if (name === 'Background Color') found.background = value;
      else if (name === 'Foreground Color') found.foreground = value;
      else if (name === 'Cursor Color') found.cursor = value;
      else if (name === 'Selection Color') found.selection = value;
    }
    return found;
  }

  function parseGhostty(text) {
    const found = {};
    for (const raw of text.split(/\r?\n/)) {
      const kv = raw.match(/^\s*([a-z-]+)\s*=\s*(.+?)\s*$/i);
      if (!kv) continue;
      const key = kv[1].toLowerCase();
      if (key === 'palette') {
        const slot = kv[2].match(/^(\d+)\s*=\s*(\S+)$/);
        if (slot && Number(slot[1]) < 16 && hex(slot[2])) found[ANSI[Number(slot[1])]] = hex(slot[2]);
      } else if (key === 'background' || key === 'foreground') {
        if (hex(kv[2])) found[key] = hex(kv[2]);
      } else if (key === 'cursor-color' && hex(kv[2])) {
        found.cursor = hex(kv[2]);
      } else if (key === 'selection-background' && hex(kv[2])) {
        found.selection = hex(kv[2]);
      }
    }
    return found;
  }

  function parseWindowsTerminal(text) {
    let o = JSON.parse(text);
    if (o && Array.isArray(o.schemes)) o = o.schemes[0];
    if (Array.isArray(o)) o = o[0];
    const found = {};
    if (!o || typeof o !== 'object') return found;
    const names = { purple: 'magenta', brightPurple: 'brightMagenta' };
    for (const [k, v] of Object.entries(o)) {
      const key = names[k] || k;
      if (ANSI.includes(key) || key === 'background' || key === 'foreground') {
        if (hex(v)) found[key] = hex(v);
      }
    }
    if (hex(o.cursorColor)) found.cursor = hex(o.cursorColor);
    if (hex(o.selectionBackground)) found.selection = hex(o.selectionBackground);
    if (typeof o.name === 'string') found.name = o.name;
    return found;
  }

  function parseXresources(text) {
    const found = {};
    for (const raw of text.split(/\r?\n/)) {
      const kv = raw.match(/^\s*[\w.*-]*?(color(\d+)|background|foreground|cursorColor)\s*:\s*(\S+)/i);
      if (!kv || !hex(kv[3])) continue;
      if (kv[2] !== undefined) {
        if (Number(kv[2]) < 16) found[ANSI[Number(kv[2])]] = hex(kv[3]);
      } else if (/^cursorColor$/i.test(kv[1])) {
        found.cursor = hex(kv[3]);
      } else {
        found[kv[1].toLowerCase()] = hex(kv[3]);
      }
    }
    return found;
  }

  /* A file's text -> { scheme } or { error }.  Which format it is comes from
     what is in it, so a file with the wrong ending still reads. */
  function parse(text, filename) {
    const body = String(text || '');
    const trimmed = body.trim();
    let found;
    try {
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        if (/^\[\s*colors/m.test(trimmed)) found = parseAlacritty(body);
        else found = parseWindowsTerminal(body);
      } else if (/<plist|Ansi 0 Color/.test(body)) {
        found = parseITerm(body);
      } else if (/^\s*\[\s*colors/m.test(body)) {
        found = parseAlacritty(body);
      } else if (/^\s*palette\s*=/m.test(body)) {
        found = parseGhostty(body);
      } else if (/color\d+\s*:/i.test(body)) {
        found = parseXresources(body);
      } else {
        return { error: 'that is not a colour scheme this client can read' };
      }
    } catch (err) {
      return { error: 'that file could not be read as a colour scheme' };
    }
    const missing = ['background', 'foreground', ...BASE].filter((k) => !found[k]);
    if (missing.length) return { error: `that scheme has no ${missing.join(', ')}` };
    const fromFile = String(filename || '').replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '')
      .replace(/[-_]+/g, ' ').trim();
    const name = (found.name || fromFile || 'Your scheme').slice(0, 40);
    const ansi = ANSI.map((k, i) => found[k] || found[ANSI[i - 8]] || '');
    const s = scheme('', name, 'your file', found.background, found.foreground,
      found.selection || '', ansi);
    s.id = 'own:' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return { scheme: s };
  }

  // --- what it looks like ----------------------------------------------------------

  function valid(s) {
    return s && typeof s.id === 'string' && hex(s.background) && hex(s.foreground)
      && ANSI.every((k) => hex(s[k]));
  }

  function ownSchemes() {
    try {
      const got = JSON.parse(store.get('colours:own', '[]'));
      return Array.isArray(got) ? got.filter(valid) : [];
    } catch (err) {
      return [];
    }
  }

  const every = () => SCHEMES.concat(ownSchemes());
  const chosen = () => every().find((s) => s.id === store.get('colours:terminal', 'dank')) || SCHEMES[0];
  const THEMES = ['dark', 'light', 'match'];
  const uiTheme = () => {
    const v = store.get('colours:ui', 'dark');
    return THEMES.includes(v) ? v : 'dark';
  };

  function terminalTheme(s) {
    const t = {
      background: s.background, foreground: s.foreground,
      // The terminal takes no input, so the cursor is the ground: a marker
      // would only suggest otherwise.
      cursor: s.background, cursorAccent: s.background,
      // Seen through, over the text, and visible on the scheme's own ground:
      // a selection you cannot see is one you do not know you have made.
      selectionBackground: alpha(s.id === 'dank' ? '#6f9beb' : s.blue, 0.45),
    };
    for (const k of ANSI) t[k] = s[k];
    return t;
  }

  //: The page's own look, as it has always been.
  const DARK = {
    '--bg': '#111318', '--panel': '#181b22', '--sunk': '#0d0f13', '--line': '#262b35',
    '--ink': '#d8dde6', '--dim': '#7d8698', '--accent': '#6f9beb',
    '--hp': '#c8553d', '--sp': '#4a90d9', '--gp': '#5aa66f', '--enemy': '#b8863b',
    '--good': '#5aa66f', '--bad': '#c8553d', '--warn': '#f2cc60',
    '--scroll': '#39404f', '--scroll-hover': '#4a5365', '--placeholder': '#4b525f',
    '--track': '#000000', '--room': '#333a48', '--room-unnamed': '#262b36', '--area-light': '34%',
  };
  const LIGHT = {
    '--bg': '#f5f6f8', '--panel': '#ffffff', '--sunk': '#eceef2', '--line': '#d3d8e0',
    '--ink': '#1e232d', '--dim': '#5d6676', '--accent': '#2f6bd1',
    '--hp': '#c0392b', '--sp': '#2a6db5', '--gp': '#2e8b57', '--enemy': '#a0620f',
    '--good': '#2e8b57', '--bad': '#c0392b', '--warn': '#9a6700',
    '--scroll': '#c3c9d3', '--scroll-hover': '#aab2bf', '--placeholder': '#9aa2af',
    '--track': '#dde1e7', '--room': '#c9d0dc', '--room-unnamed': '#dde2ea', '--area-light': '78%',
  };

  /* The page in the terminal's colours: its ground, its text, and its own
     red, green, yellow and blue for the things that are red, green, yellow
     and blue. */
  function matched(s) {
    const bg = s.background;
    const fg = s.foreground;
    const light = s.light;
    return {
      '--bg': bg, '--panel': mix(bg, fg, 0.05),
      '--sunk': mix(bg, '#000000', light ? 0.04 : 0.25), '--line': mix(bg, fg, 0.16),
      '--ink': fg, '--dim': mix(fg, bg, 0.42), '--accent': light ? s.blue : s.brightBlue,
      '--hp': s.red, '--sp': s.blue, '--gp': s.green, '--enemy': s.yellow,
      '--good': s.green, '--bad': s.red, '--warn': light ? s.yellow : s.brightYellow,
      '--scroll': mix(bg, fg, 0.22), '--scroll-hover': mix(bg, fg, 0.32),
      '--placeholder': mix(fg, bg, 0.6), '--track': light ? mix(bg, fg, 0.12) : mix(bg, '#000000', 0.5),
      '--room': mix(bg, fg, 0.2), '--room-unnamed': mix(bg, fg, 0.1),
      '--area-light': light ? '78%' : '34%',
    };
  }

  function pageColours() {
    const theme = uiTheme();
    if (theme === 'light') return { vars: LIGHT, light: true };
    if (theme === 'match') return { vars: matched(chosen()), light: chosen().light };
    return { vars: DARK, light: false };
  }

  function apply() {
    const root = document.documentElement;
    const { vars, light } = pageColours();
    for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
    root.style.setProperty('color-scheme', light ? 'light' : 'dark');
    if (root.dataset) root.dataset.theme = light ? 'light' : 'dark';
    if (window.setTerminalTheme) window.setTerminalTheme(terminalTheme(chosen()));
    // The map and the messages window draw some of their colours themselves.
    if (typeof CustomEvent !== 'undefined' && document.dispatchEvent) {
      document.dispatchEvent(new CustomEvent('themechange'));
    }
  }

  function choose(id) {
    store.set('colours:terminal', id);
    apply();
    draw();
  }

  /* Add a scheme from a file.  Returns what went wrong, or "". */
  function addScheme(text, filename) {
    const got = parse(text, filename);
    if (got.error) return got.error;
    const own = ownSchemes().filter((s) => s.id !== got.scheme.id);
    own.push(got.scheme);
    store.set('colours:own', JSON.stringify(own));
    choose(got.scheme.id);
    return '';
  }

  function removeScheme(id) {
    store.set('colours:own', JSON.stringify(ownSchemes().filter((s) => s.id !== id)));
    if (store.get('colours:terminal', 'dank') === id) store.set('colours:terminal', 'dank');
    apply();
    draw();
  }

  window.colours = {
    SCHEMES, ANSI, parse, hex, mix, addScheme, removeScheme, choose, apply,
    terminalTheme: () => terminalTheme(chosen()),
    chosen, uiTheme,
  };

  // --- the pane --------------------------------------------------------------------

  function swatch(colour) {
    const b = document.createElement('i');
    b.className = 'sw';
    b.style.background = colour;
    return b;
  }

  //: What 3K looks like in it: a room, a fight, a tell, a channel, the prompt.
  const SAMPLE = [
    // In the text colour rather than bright white: Solarized Light's bright
    // white is its own ground, and a preview whose first line vanishes looks
    // broken rather than honest.
    [['foreground', 'The Center of Town'], ['brightBlack', ' (e,w,s,n,d,omp,jump)']],
    [['red', 'Cur'], ['foreground', ' snaps at you and misses.  '], ['brightGreen', 'You hit Cur hard.']],
    [['green', 'Friend'], ['foreground', ' tells you: '], ['brightYellow', 'ready when you are']],
    [['cyan', '[newbie] '], ['foreground', 'Someone: '], ['magenta', 'hello all']],
    [['brightBlack', 'HP: '], ['green', '31207/31207'], ['brightBlack', '  SP: '], ['blue', '3971/3971'],
      ['brightBlack', '  > ']],
  ];

  function drawPreview(s) {
    const box = $('scheme-preview');
    if (!box) return;
    box.style.background = s.background;
    box.style.color = s.foreground;
    const lines = SAMPLE.map((parts) => {
      const line = document.createElement('div');
      line.append(...parts.map(([k, text]) => {
        const span = document.createElement('span');
        span.style.color = s[k];
        span.textContent = text;
        return span;
      }));
      return line;
    });
    const row = document.createElement('div');
    row.className = 'sw-row';
    row.append(...ANSI.map((k) => swatch(s[k])));
    box.replaceChildren(...lines, row);
  }

  function draw() {
    const list = $('scheme-list');
    if (!list) return;
    const current = chosen();
    list.replaceChildren(...every().map((s) => {
      const row = document.createElement('div');
      row.className = 'scheme' + (s.id === current.id ? ' on' : '');
      row.title = `${s.name}, from ${s.by}`;
      const name = document.createElement('b');
      name.textContent = s.name;
      const by = document.createElement('small');
      by.textContent = s.by;
      const sws = document.createElement('span');
      sws.className = 'sws';
      sws.style.background = s.background;
      sws.append(...ANSI.slice(0, 8).map((k) => swatch(s[k])));
      row.append(name, by, sws);
      row.onclick = () => choose(s.id);
      if (s.id.startsWith('own:')) {
        const x = document.createElement('button');
        x.type = 'button';
        x.textContent = '×';
        x.title = 'Remove this scheme';
        x.onclick = (e) => {
          if (e && e.stopPropagation) e.stopPropagation();
          removeScheme(s.id);
        };
        row.append(x);
      }
      return row;
    }));
    drawPreview(current);
    const theme = $('ui-theme');
    if (theme) theme.value = uiTheme();
  }

  apply();
  if (!$('scheme-list')) return;

  $('ui-theme').onchange = () => {
    store.set('colours:ui', $('ui-theme').value);
    apply();
    draw();
  };
  $('scheme-import').onclick = () => $('scheme-file').click();
  $('scheme-file').onchange = () => {
    const file = $('scheme-file').files && $('scheme-file').files[0];
    if (!file) return;
    // A scheme is a few kilobytes; a file picked by mistake should not stall the page.
    if (file.size > 256 * 1024) {
      $('scheme-error').textContent = 'that file is too big to be a colour scheme';
      $('scheme-file').value = '';
      return;
    }
    file.text().then((text) => {
      $('scheme-error').textContent = addScheme(text, file.name);
      $('scheme-file').value = '';
    });
  };
  $('colours-reset').onclick = () => {
    store.set('colours:terminal', 'dank');
    store.set('colours:ui', 'dark');
    $('scheme-error').textContent = '';
    apply();
    draw();
  };
  draw();
})();
