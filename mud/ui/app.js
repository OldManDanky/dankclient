/* The browser draws; Python owns the socket, the protocol and the state.
   Incoming: {t:"text"|"state"|"tell"|"chat"}.  Outgoing: {t:"cmd", d:"..."} */

const $ = (id) => document.getElementById(id);

// Surface failures in the UI.  A silent throw up here used to leave the status
// line reading "connecting..." forever, which says nothing about the cause.
function fail(what, err) {
  const s = $('status');
  if (s) {
    s.className = '';
    s.style.color = '#c8553d';
    s.textContent = `${what}: ${err && err.message ? err.message : err}`;
  }
  console.error(what, err);
}
addEventListener('error', (e) => fail('script error', e.message));

/* How wide the terminal is allowed to get.

   3k.org draws to about eighty columns -- its own ASCII map is 78 wide and
   prose wraps well short of that -- so a full-screen window leaves a lot of
   empty terminal.  The cap gathers that space into one piece on the right,
   where the floating panels live, instead of spreading it across every line.

   Off by default, though.  Capping it sounds right and looks wrong however
   generously it is set: the text ends up in a block with a margin beside it,
   and a margin is not the same thing as a tidy edge.  The sidebar is where
   the width goes instead -- it has something to do with it.

   The cap is in columns rather than pixels because columns are the unit the
   MUD writes in; the width in pixels depends on the font and is measured. */
const WIDTH_KEY = 'term:cols';
const DEFAULT_COLS = 0;
let wantCols = DEFAULT_COLS;
let perCol = 0;                  // pixels per column, measured once

try {
  const saved = localStorage.getItem(WIDTH_KEY);
  if (saved !== null) wantCols = parseInt(saved, 10) || 0;
} catch (err) { /* private window: the default it is */ }

// The terminal's own gutter, read rather than assumed: it comes from --gut,
// which every other outer edge shares.
function gutter() {
  const cs = getComputedStyle($('term'));
  return parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
}

function measure() {
  const out = $('out');
  out.style.maxWidth = '';
  fit.fit();
  if (term && term.cols > 0) {
    perCol = (out.clientWidth - gutter()) / term.cols;
  }
}

/* Fit the terminal to its box, capping the output column if asked.

   The cap goes on the output area rather than on the terminal, so the
   messages window above it narrows by exactly the same amount and the two
   scrollbars stay on one line.

   Measuring is the delicate part.  Clearing the cap to measure and setting it
   again makes the box change twice, and the observer watching that box calls
   this again -- back and forth for ever.  So the width of a column is
   measured once, uncapped, and kept: it is a property of the font, and the
   font does not change with the window. */
function refit() {
  if (!fit) return;
  try {
    if (wantCols <= 0) {
      measure();                 // uncapped: no second pass to oscillate with
      return;
    }
    if (!perCol) measure();
    const want = Math.round(wantCols * perCol + gutter());
    const px = want + 'px';
    // Setting the same value again changes nothing, so the observer that
    // brought us here does not fire a second time.
    if ($('out').style.maxWidth !== px) {
      $('out').style.maxWidth = px;
    }
    fit.fit();
  } catch (err) {
    /* mid-layout; the next resize will do it */
  }
}

/* Set the cap, in columns.  0 means as wide as the window allows. */
window.setTerminalWidth = function (cols) {
  wantCols = cols > 0 ? cols : 0;
  try {
    localStorage.setItem(WIDTH_KEY, String(wantCols));
  } catch (err) { /* it just will not stick */ }
  refit();
};

window.terminalWidth = () => wantCols;

/* The terminal's font: the one chosen, then a stack of fixed-width fonts
   behind it, so a font that has since been uninstalled still leaves one that
   keeps 3K's columns in line. */
function fontStack(name) {
  const safe = String(name || '').replace(/["\\;{}]/g, '').trim();
  return (safe ? `"${safe}", ` : '') + 'Consolas, "DejaVu Sans Mono", monospace';
}
window.fontStack = fontStack;

/* Change it while it is running.  The width of a column is a property of the
   font -- refit() measures it once and keeps it -- so it is measured again. */
window.setTerminalFont = function (family, size, line) {
  if (!term) return;
  term.options.fontFamily = fontStack(family);
  term.options.fontSize = size;
  term.options.lineHeight = line;
  perCol = 0;
  refit();
};

/* What it actually came out at, which is not always what was asked for: a
   narrow window gives you fewer columns than any cap. */
window.terminalCols = () => (term ? term.cols : 0);

let term = null;
let fit = null;
try {
  if (typeof Terminal === 'undefined') throw new Error('xterm.js did not load');
  term = new Terminal({
    // What was chosen under Options -> Fonts, from the start, rather than the
    // default for a moment and then the choice.
    fontFamily: fontStack(window.prefs.get('font:family', '')),
    fontSize: parseInt(window.prefs.get('font:size', '14'), 10) || 14,
    lineHeight: parseFloat(window.prefs.get('font:line', '1')) || 1,
    scrollback: 50000,
    cursorBlink: false,
    // Output only -- the input bar owns the keyboard.  Without this xterm
    // swallows keystrokes into its hidden textarea and typing appears to do
    // nothing until you click the input again.
    disableStdin: true,
    // cursor matches the ground: the terminal takes no input, so the marker
    // would only suggest otherwise
    theme: { background: '#111318', foreground: '#d8dde6',
             cursor: '#111318', cursorAccent: '#111318',
             // Visible against the ground: a selection you cannot see is one
             // you do not know you have made before pressing Ctrl+C.
             selectionBackground: 'rgba(111, 155, 235, 0.45)' },
  });
  if (typeof FitAddon !== 'undefined') {
    fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
  }
  term.open($('term'));
  refit();
  addEventListener('resize', refit);
  // The status strip grows when the guild line arrives and wraps on a narrow
  // window; the messages window above can be collapsed or switched off.  All
  // of them change the terminal's box without a window resize, and none of
  // them change the output area's, so the terminal is the box to watch.
  //
  // Which is also the box refit sizes, and that used to be a loop: it cleared
  // the cap to measure and set it again, so the observer saw two changes and
  // called it back.  A column's width is measured once now and kept, so a
  // second call sets the same value, nothing moves, and it stops.
  if (fit && typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => refit()).observe($('term'));
  }
} catch (err) {
  fail('terminal', err);
}

let ws = null;
let lastRound = null;


// Panels that have to ask the server for something -- the rule list, the
// routes -- need to know when there is a socket to ask down.  Sending at load
// time raced the handshake and threw; the only reason it ever worked is that
// the send was the last line in the file.
const onConnected = [];
window.whenConnected = (fn) => {
  onConnected.push(fn);
  if (ws && ws.readyState === 1) fn();
};

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  window.ws = ws;
  ws.onopen = () => {
    $('status').textContent = 'connected';
    $('status').className = 'live';
    for (const fn of onConnected) {
      try {
        fn();
      } catch (err) {
        console.error('on connect', err);
      }
    }
  };
  ws.onclose = () => {
    $('status').textContent = 'disconnected - retrying';
    $('status').className = '';
    setTimeout(connect, 2000);
  };
  ws.onmessage = (e) => handle(JSON.parse(e.data));
}

/* What was on screen before this terminal opened.

   A refresh emptied it, and a refresh is what you do after every change to the
   client -- so the answer to "what just happened" went away exactly when you
   wanted it. It comes from the log, which stores lines with the ANSI stripped
   out, so it comes back without colour. Dimmed and ruled off rather than
   dressed up as live text: this is what happened, not what is happening. */
function restore(lines) {
  if (!term || !lines || !lines.length) return;
  for (const line of lines) {
    // The log is plain text, but it is text the MUD sent -- keep a stray
    // control character from steering the terminal.
    const text = String(line.text || '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '');
    term.write(`\x1b[2m${line.kind === 'sent' ? '> ' : ''}${text}\x1b[0m\r\n`);
  }
  const wide = Math.max(8, Math.min(window.terminalCols ? window.terminalCols() : 80, 100));
  const label = ' before the refresh ';
  const rule = '\u2500'.repeat(Math.max(1, Math.floor((wide - label.length) / 2)));
  term.write(`\x1b[2m${rule}${label}${rule}\x1b[0m\r\n`);
}

function handle(m) {
  if (m.t === 'text') {
    if (term) term.write(m.d);
  } else if (m.t === 'back') {
    restore(m.lines);
  } else if (m.t === 'state') {
    render(m);
  } else if (m.t === 'tell' || m.t === 'chat') {
    // The MUD prints these in the main output already; echoing them into the
    // terminal made a third copy.  The monitor is the second.
    if (window.pushMessage) window.pushMessage(m.t, m.d);
  } else if (m.t === 'rules' && window.handleRules) {
    window.handleRules(m);
  } else if (m.t === 'routes' && window.handleRoutes) {
    window.handleRoutes(m);
  } else if (m.t === 'login' && window.handleLogin) {
    window.handleLogin(m);
  } else if (m.t === 'update' && window.handleUpdate) {
    window.handleUpdate(m);
  } else if (m.t === 'help' && window.handleHelp) {
    window.handleHelp(m);
  }
}

// Input lives in one place at the bottom rather than being echoed into the
// scrollback as you type, so what you are composing never gets shredded by
// output arriving mid-keystroke.
const cmd = $('cmd');
const history = [];
let histPos = 0;

/* Keep the last command: it stays in the box, selected, so Enter sends it
   again and typing anything replaces it.  Portal did this, and it is what
   sending the same thing over and over wants.  A preference of the screen,
   not the character, like the rest of Panels. */
const keepCmd = $('keep-cmd');
if (keepCmd) {
  keepCmd.checked = window.prefs.get('keep-cmd', '0') === '1';
  keepCmd.onchange = () => {
    window.prefs.set('keep-cmd', keepCmd.checked ? '1' : '0');
    cmd.focus();
  };
}

$('bar').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = cmd.value;
  // One entry for a command sent ten times running, not ten.
  if (text && history[history.length - 1] !== text) {
    history.push(text);
    if (history.length > 500) history.shift();
  }
  histPos = history.length;
  if (keepCmd && keepCmd.checked && text) {
    cmd.select();
  } else {
    cmd.value = '';
  }
  send(text, true);
});

cmd.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowUp') {
    if (histPos > 0) {
      histPos -= 1;
      cmd.value = history[histPos];
      cmd.setSelectionRange(cmd.value.length, cmd.value.length);
    }
    e.preventDefault();
  } else if (e.key === 'ArrowDown') {
    histPos = Math.min(histPos + 1, history.length);
    cmd.value = histPos === history.length ? '' : history[histPos];
    e.preventDefault();
  } else if (e.key === 'PageUp' || e.key === 'PageDown') {
    if (term) term.scrollPages(e.key === 'PageUp' ? -1 : 1);
    e.preventDefault();
  }
});

// Typing anywhere goes to the command bar, so you never have to click first.
// Two exceptions pull in opposite directions: never steal focus from a real
// field (that made the triggers panel untypeable), but xterm's hidden textarea
// is not a real field -- selecting text in the terminal used to leave the
// keyboard pointing at nothing.
addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  const t = e.target;
  const closest = t && t.closest ? (sel) => t.closest(sel) : () => null;
  const inField = closest('input, textarea, select, [contenteditable]');
  if (inField && !closest('#term')) return;
  if (e.key.length === 1 || e.key === 'Backspace') cmd.focus();
});

// Clicking the terminal is for selecting text; it should not capture typing.
// The selection survives the input taking focus back -- it is xterm's own,
// not the page's -- and Ctrl+C below is what copies it.
$('term').addEventListener('mouseup', () => {
  if (!getSelection || String(getSelection()) === '') cmd.focus();
});

/* Ctrl+C copies what is selected in the terminal.  Drag to select, double-
   click for a word, triple-click for the whole line.

   It did nothing before: the keyboard is always pointed at the command bar,
   and xterm's selection is its own rather than the page's, so the browser's
   copy found nothing to copy.  A selection in the command bar itself still
   wins -- that is the text somebody is working on -- and so does one made
   anywhere else on the page. */
function copyText(text) {
  const fallback = () => {
    const box = document.createElement('textarea');
    box.value = text;
    box.setAttribute('readonly', '');
    box.style.position = 'fixed';
    box.style.opacity = '0';
    document.body.append(box);
    box.select();
    try { document.execCommand('copy'); } catch (err) { /* nothing to do */ }
    box.remove();
    cmd.focus();
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(fallback);
  } else {
    fallback();
  }
}

addEventListener('keydown', (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey || e.key.toLowerCase() !== 'c') return;
  if (!term || !term.hasSelection()) return;
  const t = e.target;
  if (t && typeof t.selectionStart === 'number' && t.selectionStart !== t.selectionEnd) return;
  if (getSelection && String(getSelection()) !== '') return;
  e.preventDefault();
  copyText(term.getSelection());
  // Cleared, the way a terminal does it: the selection going is how you can
  // tell the copy happened.
  term.clearSelection();
});

/* Addresses in the output open with shift-click.

   Shift, because a plain click in the terminal is for selecting text, and a
   link that fires on the click that was meant to start a selection is a link
   that opens by accident.  The address goes to the server rather than to
   window.open: in app mode window.open opens inside the client's own private
   browser, with none of the player's bookmarks or logins, and the server hands
   it to the browser they actually use -- after checking it is http or https,
   because anybody on 3K can put text on this screen. */
const ADDRESS = /\bhttps?:\/\/[^\s"'<>`]+/g;

function openLink(url) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ t: 'open', url }));
}

if (term && term.registerLinkProvider) {
  term.registerLinkProvider({
    provideLinks(y, callback) {
      const row = term.buffer.active.getLine(y - 1);
      if (!row) { callback(undefined); return; }
      const text = row.translateToString(true);
      const links = [];
      for (const m of text.matchAll(ADDRESS)) {
        // A sentence ends after the address, not inside it.
        const url = m[0].replace(/[.,;:!?'")\]}]+$/, '');
        if (!url) continue;
        links.push({
          range: { start: { x: m.index + 1, y }, end: { x: m.index + url.length, y } },
          text: url,
          decorations: { underline: true, pointerCursor: false },
          activate(event, address) { if (event.shiftKey) openLink(address); },
          hover() { $('term').title = 'Shift-click to open'; },
          leave() { $('term').title = ''; },
        });
      }
      callback(links.length ? links : undefined);
    },
  });
}

// These are commands going to somebody's character, so the first press shows
// what they are and the second sends them.  A button that fires thirteen
// settings unseen is a button nobody should press.
$('set-prefixes').addEventListener('click', () => {
  const armed = $('set-prefixes').dataset.armed === '1';
  send('/prefixes' + (armed ? ' set' : ''), false);
  $('set-prefixes').dataset.armed = armed ? '' : '1';
  $('set-prefixes').textContent = armed
    ? 'Set ANSI prefixes' : 'Send them \u2014 click again';
  if (armed) {
    setTimeout(() => { $('set-prefixes').dataset.armed = ''; }, 100);
  } else {
    // Disarm on its own, so a stray click ten minutes later does nothing.
    setTimeout(() => {
      $('set-prefixes').dataset.armed = '';
      $('set-prefixes').textContent = 'Set ANSI prefixes';
    }, 20000);
  }
});

$('mip').addEventListener('click', () => {
  if (ws) ws.send(JSON.stringify({ t: 'jumpstart' }));
  cmd.focus();
});

function link(op) {
  if (ws) ws.send(JSON.stringify({ t: 'link', op }));
}

$('link-again').addEventListener('click', () => {
  if (window.openLogin) window.openLogin();
});

// The client stays up either way: what closes is the connection, not the
// window, so the map, the log and everything in Options are still here to come
// back to. Confirmed because a mis-click leaves you link-dead in whatever room
// you were standing in.
$('hangup').addEventListener('click', () => {
  if (confirm('Save the session and disconnect from 3K?')) link('hangup');
  cmd.focus();
});

function send(text, echo) {
  if (ws) ws.send(JSON.stringify({ t: 'cmd', d: text }));
  if (echo && term) term.write(`\x1b[2m> ${text}\x1b[0m\r\n`);
  cmd.focus();
}

// Gauge names: whatever MIP says (BBA/BBB/BBC/BBD), else whatever you have
// called it, else the protocol's own name.  3k.org sends no labels, so in
// practice this is your own naming.
const DEFAULT_LABELS = { hp: 'HP', sp: 'SP', gp1: 'GP1', gp2: 'GP2' };
let mipLabels = {};

function ownLabel(key) {
  try {
    return localStorage.getItem('label:' + key) || '';
  } catch (err) {
    return '';
  }
}

function labelFor(key) {
  return mipLabels[key] || ownLabel(key) || DEFAULT_LABELS[key];
}

function paintLabels() {
  for (const key of Object.keys(DEFAULT_LABELS)) {
    const el = $('lbl-' + key);
    if (el) {
      el.textContent = labelFor(key);
      el.title = mipLabels[key]
        ? 'Named by the MUD'
        : 'Click to rename this gauge';
    }
  }
}

for (const key of Object.keys(DEFAULT_LABELS)) {
  const el = $('lbl-' + key);
  if (!el) continue;
  el.style.cursor = 'pointer';
  el.onclick = () => {
    if (mipLabels[key]) return;              // the MUD named it; leave it be
    const next = prompt(`Name for ${DEFAULT_LABELS[key]}`, labelFor(key));
    if (next === null) return;
    try {
      if (next.trim()) localStorage.setItem('label:' + key, next.trim());
      else localStorage.removeItem('label:' + key);
    } catch (err) { /* private window: the name just will not stick */ }
    paintLabels();
  };
}
paintLabels();

function bar(pct, nEl, bEl, text) {
  $(nEl).textContent = text === null || text === undefined ? '–' : text;
  const w = pct === null || pct === undefined ? 0 : Math.max(0, Math.min(100, pct));
  $(bEl).style.width = w + '%';
}

const pair = (cur, max) =>
  cur === null || cur === undefined ? null : max ? `${cur} / ${max}` : `${cur}`;

function render(s) {
  const p = s.player;

  bar(p.hp_pct, 'hp-n', 'hp-b', pair(p.hp, p.max_hp));
  bar(p.sp_pct, 'sp-n', 'sp-b', pair(p.sp, p.max_sp));
  bar(p.max_gp1 ? (100 * p.gp1) / p.max_gp1 : null, 'g1-n', 'g1-b', pair(p.gp1, p.max_gp1));
  bar(p.max_gp2 ? (100 * p.gp2) / p.max_gp2 : null, 'g2-n', 'g2-b', pair(p.gp2, p.max_gp2));

  // Driven by N, the round counter, so the bar steps once per round rather
  // than jittering on both composites the MUD sends each round.
  const raw = s.enemy_label || p.enemy || '';
  const fighting = raw !== '';
  $('combat').hidden = !fighting;
  if (fighting) {
    const marks = [...raw.matchAll(/[{[]([^}\]]*)[}\]]/g)].map((m) => m[1]);
    $('enemy-name').textContent = raw.replace(/\s*[{[][^}\]]*[}\]]/g, '').trim();
    $('enemy-marks').textContent = marks.join(' · ');
    bar(p.enemy_pct, 'en-n', 'en-b', p.enemy_pct === null ? null : p.enemy_pct + '%');
    if (p.round !== null && p.round !== lastRound) {
      lastRound = p.round;
      $('round').textContent = p.round ? `round ${p.round}` : '';
    }
  } else {
    lastRound = null;
    $('round').textContent = '';
  }

  $('room-name').textContent = s.room.short || '';

  const exits = $('exits');
  exits.replaceChildren();
  for (const e of s.room.exits) {
    const b = document.createElement('button');
    b.textContent = e;
    b.onclick = () => send(e, true);
    exits.append(b);
  }

  const ul = $('contents');
  ul.replaceChildren();
  const all = [...s.room.contents, ...s.room.scenery];
  if (all.length === 0) {
    const li = document.createElement('li');
    li.className = 'none';
    li.textContent = 'empty';
    ul.append(li);
  }
  for (const o of all) {
    const li = document.createElement('li');

    const kind = document.createElement('span');
    kind.className = 'kind';
    kind.textContent = o.kind;

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = o.name;
    name.title = o.description;

    const acts = document.createElement('span');
    acts.className = 'acts';
    // The MUD tells us which commands are valid for each object; #N is its name.
    for (const tmpl of o.actions.slice(0, 3)) {
      const b = document.createElement('button');
      b.textContent = tmpl.split(' ')[0];
      b.title = tmpl.replaceAll('#N', o.name);
      b.onclick = () => send(tmpl.replaceAll('#N', o.name), true);
      acts.append(b);
    }

    li.append(kind, name, acts);
    ul.append(li);
  }

  const g = Object.entries(p.gline || {});
  $('guild').hidden = g.length === 0;
  const gl = $('gline');
  gl.replaceChildren();
  for (const [label, f] of g) {
    const row = document.createElement('div');
    const b = document.createElement('b');
    b.textContent = label;
    const v = document.createElement('span');
    v.textContent = f.value;
    if (f.status) v.className = 'g-' + f.status;
    row.append(b, v);
    gl.append(row);
  }

  if (window.renderWho) window.renderWho(s.who);

  if (s.messages && window.seedMessages) window.seedMessages(s.messages);
  if (s.where && window.renderAbout) window.renderAbout(s.where);
  if (s.release && window.renderRelease) window.renderRelease(s.release);

  if (s.labels && JSON.stringify(s.labels) !== JSON.stringify(mipLabels)) {
    mipLabels = s.labels;
    paintLabels();
  }

  if (window.renderMap) window.renderMap(s.map);

  if (s.apm) {
    const { rate, soft, limit } = s.apm;
    const box = $('apm');
    box.className = rate >= limit ? 'hot' : rate >= soft ? 'warn' : '';
    $('apm-n').textContent = `${rate} / ${limit}` +
      (s.apm.queued ? `  (${s.apm.queued} held)` : '');
    $('apm-b').style.width = Math.min(100, (100 * rate) / (limit || 1)) + '%';
  }

  // The connection, before anything that depends on having one.  A dropped
  // link shows as a terminal that has simply stopped saying anything, so this
  // is the only place the reason appears.
  // Text only.  This used to rebuild the panel from scratch on every push,
  // which while disconnected is ten times a second -- so the button under the
  // cursor was a different button by the time the mouse came back up, and the
  // click never landed on anything.
  const box = $('link');
  if (s.link && !s.link.up) {
    box.hidden = false;
    let why = '';
    if (s.link.reconnect) {
      why = s.link.in ? ` \u2014 reconnecting in ${s.link.in}s`
                      : ' \u2014 reconnecting\u2026';
      if (s.link.attempts > 1) why += ` (attempt ${s.link.attempts})`;
    }
    $('link-why').textContent = why;
    // Nothing is bringing it back by itself, so the way back is here: the
    // same screen that asks who is playing, because that is the question.
    $('link-again').hidden = !!s.link.reconnect;
  } else {
    box.hidden = true;
  }

  const mip = $('mip');
  if (s.quiet && s.quiet.length) {
    // A code the MUD has stopped sending says nothing about itself; the only
    // sign is the room panel quietly emptying.
    mip.className = 'warn';
    mip.textContent = 'not being sent: ' + s.quiet.join(', ');
  } else if (s.mip) {
    const live = s.mip.seen;
    mip.className = live ? 'live' : 'waiting';
    mip.textContent = live
      ? `MIP live \u00b7 ${s.mip.codes} msgs \u00b7 code ${s.mip.sec}`
      : `MIP: waiting \u2014 click to re-send handshake`;
  }

  const chrome = $('chrome');
  chrome.replaceChildren();
  for (const [k, v] of Object.entries(s.chrome)) {
    if (!v) continue;
    const span = document.createElement('span');
    span.textContent = `${k}: ${v}`;
    chrome.append(span);
  }
}

window.focusInput = () => cmd.focus();

connect();          // independent of the terminal, so data flows regardless
cmd.focus();
