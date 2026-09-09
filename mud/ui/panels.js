/* What is on screen.

   The room panel is off unless it is asked for.  It lists what is in the room
   with a button for every action the MUD says each thing takes, which is worth
   having and is not worth a third of the sidebar when you are not using it --
   so it is the panel you consult, not the one you watch, and it sits at the
   bottom when it is on at all.

   A layout preference belongs to the browser rather than to the character: it
   is about the screen in front of you, and a second window on a second monitor
   can reasonably want a different one. */

(function () {
  const $ = (id) => document.getElementById(id);
  const store = window.prefs;

  // In the order they sit on screen.
  const PANELS = [
    { id: 'msgmon', label: 'Messages', on: true,
      note: 'Tells, emotes and channel traffic, across the top of the '
          + 'output. Each channel gets a tag you can switch off.' },
    { id: 'mapmon', label: 'Map', on: true,
      note: 'Top of the sidebar. Click a room to walk there.' },
    { id: 'roompanel', label: 'Room contents and exits', on: false,
      note: 'Bottom of the sidebar, with a button for every action the MUD '
          + 'says a thing takes.' },
  ];

  const key = (id) => `panel:${id}:shown`;

  function shown(p) {
    const saved = store ? store.get(key(p.id), null) : null;
    return saved === null ? p.on : saved === '1';
  }

  function apply(p) {
    const el = $(p.id);
    if (!el) return;
    const on = shown(p);
    el.hidden = !on;
    // The map draws into a canvas sized from its box, and a box that was
    // display:none has no size -- so it has to be told to draw again once it
    // has one.
    if (on && p.id === 'mapmon' && window.renderMap) window.renderMap();
  }

  function set(p, on) {
    if (store) store.set(key(p.id), on ? '1' : '');
    apply(p);
  }

  function render() {
    const box = $('panel-toggles');
    if (!box) return;
    box.replaceChildren();
    for (const p of PANELS) {
      const row = document.createElement('div');
      row.className = 'frow';

      const label = document.createElement('label');
      label.className = 'check';
      const box2 = document.createElement('input');
      box2.type = 'checkbox';
      box2.checked = shown(p);
      box2.onchange = () => set(p, box2.checked);
      label.append(box2, document.createTextNode(p.label));

      const note = document.createElement('p');
      note.className = 'fhint';
      note.textContent = p.note;

      // One column: the checkbox is its own label, so a second one beside it
      // would just be the same words twice.
      row.style.gridTemplateColumns = 'minmax(0,1fr)';
      row.append(label, note);
      box.append(row);
    }
    if (window.options) {
      window.options.count('panels', PANELS.filter(shown).length);
    }
  }

  // --- how wide the terminal is allowed to get -----------------------------

  const WIDTHS = [
    { cols: 0, label: 'As wide as the window' },
    { cols: 80, label: '80 columns — what the MUD draws to' },
    { cols: 100, label: '100 columns' },
    { cols: 120, label: '120 columns' },
    { cols: 140, label: '140 columns' },
    { cols: 160, label: '160 columns' },
  ];

  function renderWidth() {
    const sel = $('term-cols');
    if (!sel || !window.setTerminalWidth) return;
    sel.replaceChildren();
    for (const w of WIDTHS) {
      const o = document.createElement('option');
      o.value = String(w.cols);
      o.textContent = w.label;
      sel.append(o);
    }
    sel.value = String(window.terminalWidth ? window.terminalWidth() : 100);
    sel.onchange = () => {
      window.setTerminalWidth(parseInt(sel.value, 10) || 0);
      showWidth();
    };
    showWidth();
  }

  function showWidth() {
    // What it actually came out at, which is not always what was asked for:
    // a narrow window gives you fewer columns than any cap.
    const now = $('term-cols-now');
    const cols = window.terminalCols ? window.terminalCols() : 0;
    if (now) now.textContent = cols ? `now ${cols}` : '';
  }

  for (const p of PANELS) apply(p);
  render();
  renderWidth();
  window.renderPanels = () => {
    render();
    renderWidth();
  };
})();
