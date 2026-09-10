/* The numpad as a way to walk: 8 north, 2 south, and so on, each key set to
   any command in Options -> Panels.

   Off unless asked for -- a new player pressing 8 on the numpad expects an 8.
   When it is on, the usual choice is "when the command box is empty": walk
   without thinking, and mid-sentence it is still a number pad.  A box whose
   whole text is selected counts as empty, because that is what "keep the
   last command" leaves and a key pressed then would replace it anyway.

   The browser says which physical key it was (Numpad8, not "8"), with NumLock
   on or off, so the digit row above the letters is never involved.  Holding a
   key sends once: auto-repeat would send "n" thirty times a second, which on
   a strange map is how you walk into something.  A key left empty types its
   number, so any one of them can be handed back. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;

  //: Browser key code -> the key's own label.
  const KEYS = {
    Numpad7: '7', Numpad8: '8', Numpad9: '9',
    Numpad4: '4', Numpad5: '5', Numpad6: '6',
    Numpad1: '1', Numpad2: '2', Numpad3: '3',
    Numpad0: '0', NumpadDecimal: '.',
    NumpadDivide: '/', NumpadMultiply: '*',
    NumpadSubtract: '-', NumpadAdd: '+',
  };
  const DEFAULTS = {
    7: 'nw', 8: 'n', 9: 'ne',
    4: 'w', 5: 'look;search', 6: 'e',
    1: 'sw', 2: 's', 3: 'se',
    0: '', '.': '', '/': '', '*': '', '-': 'd', '+': 'u',
  };
  //: The grid, in the order a numpad is laid out.  "fixed" keys are shown for
  //: their place and cannot be set.
  const LAYOUT = [
    ['Num', 'fixed'], ['/'], ['*'], ['-'],
    ['7'], ['8'], ['9'], ['+', 'tall'],
    ['4'], ['5'], ['6'],
    ['1'], ['2'], ['3'], ['Enter', 'fixed tall'],
    ['0', 'wide'], ['.'],
  ];

  let mode = 'off';
  let map = Object.assign({}, DEFAULTS);

  function load() {
    mode = store.get('numpad:mode', 'off');
    if (!['off', 'empty', 'always'].includes(mode)) mode = 'off';
    map = Object.assign({}, DEFAULTS);
    try {
      const got = JSON.parse(store.get('numpad:map', '{}'));
      for (const key of Object.keys(DEFAULTS)) {
        if (typeof got[key] === 'string') map[key] = got[key];
      }
    } catch (err) { /* a bad preference is no preference */ }
  }

  function save() {
    store.set('numpad:mode', mode);
    store.set('numpad:map', JSON.stringify(map));
  }

  // --- the keys --------------------------------------------------------------

  /* Is the command box, as it stands, somewhere a key would replace? */
  function boxIsFree(box) {
    const text = box.value || '';
    if (!text) return true;
    return box.selectionStart === 0 && box.selectionEnd === text.length;
  }

  window.numpadKey = function (e) {
    const key = KEYS[e.code];
    if (!key || mode === 'off') return false;
    if (e.ctrlKey || e.altKey || e.metaKey) return false;
    const box = $('cmd');
    const t = e.target;
    const closest = t && t.closest ? (sel) => t.closest(sel) : () => null;
    // A real field somewhere else -- a trigger being written -- keeps its keys.
    if (t && t !== box && closest('input, textarea, select, [contenteditable]')
        && !closest('#term')) return false;
    if (mode === 'empty' && box && !boxIsFree(box)) return false;
    const command = (map[key] || '').trim();
    if (!command) return false;           // unset: it types its number
    e.preventDefault();
    // Taken, so nothing else on the page sees it.  With NumLock off the keys
    // are also the arrows and PageUp: 8 moved through the command history as
    // well as walking north, and 9 scrolled the terminal up a page, where it
    // stayed while everything new arrived out of sight below.
    if (e.stopPropagation) e.stopPropagation();
    if (e.repeat) return true;            // held down: once is enough
    const parts = command.split(';').map((s) => s.trim()).filter(Boolean);
    for (const part of parts) if (window.sendCommand) window.sendCommand(part);
    return true;
  };
  // Capturing, on the way down: first, before the command box's own arrow
  // and PageUp handling, which would otherwise have acted on it already.
  addEventListener('keydown', window.numpadKey, true);

  // --- Options -> Panels -----------------------------------------------------

  function grid() {
    const into = $('numpad-grid');
    if (!into) return;
    into.replaceChildren();
    for (const [label, kind] of LAYOUT) {
      const cell = document.createElement('label');
      cell.className = 'nk' + (kind ? ` ${kind}` : '');
      const name = document.createElement('b');
      name.textContent = label;
      cell.append(name);
      if (kind && kind.includes('fixed')) {
        const what = document.createElement('span');
        what.textContent = label === 'Enter' ? 'sends the box' : '';
        cell.append(what);
      } else {
        const input = document.createElement('input');
        input.type = 'text';
        input.spellcheck = false;
        input.autocomplete = 'off';
        input.value = map[label] || '';
        input.placeholder = label;
        input.setAttribute('aria-label', `numpad ${label}`);
        input.oninput = () => {
          map[label] = input.value;
          save();
        };
        cell.append(input);
      }
      into.append(cell);
    }
  }

  load();
  if ($('numpad-mode')) {
    $('numpad-mode').value = mode;
    $('numpad-mode').onchange = () => {
      mode = $('numpad-mode').value;
      save();
    };
  }
  if ($('numpad-reset')) {
    $('numpad-reset').onclick = () => {
      map = Object.assign({}, DEFAULTS);
      save();
      grid();
    };
  }
  grid();
})();
