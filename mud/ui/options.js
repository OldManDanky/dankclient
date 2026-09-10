/* The options panel: one place for routes, rules and character setup.

   Three buttons on the sidebar became three flyouts that could each be open
   over the other, and nothing said which settings lived where.  This owns the
   frame -- the rail, which pane is showing, and the editor that covers them --
   and rules.js and routes.js fill it in.

   An editor is a layer over the panes rather than a form inside one: the form
   is longer than the list it came from, and a list scrolled halfway down with
   a form growing out of the middle of it is hard to read and easy to lose your
   place in. */

(function () {
  const $ = (id) => document.getElementById(id);
  const panel = $('options');
  const tabs = [...$('opt-tabs').querySelectorAll('button[data-tab]')];
  const panes = [...document.querySelectorAll('.opt-pane')];
  const editors = [...document.querySelectorAll('.opt-editor')];

  //: the tabs whose lists come from the rules store
  const RULE_TABS = new Set(['trigger', 'alias', 'event', 'watch', 'timer']);
  //: ...of which these are the ones a line of text can be tried against.  A
  //: timer does not match anything; it just comes round.
  const TESTABLE = new Set(['trigger', 'alias', 'event', 'watch']);
  //: the tabs that show a list, and so have something to search
  const LIST_TABS = new Set([...RULE_TABS, 'routes', 'scripts', 'marks']);
  const LAST = 'opt:tab';

  let current = 'routes';

  function remember(name) {
    try {
      localStorage.setItem(LAST, name);
    } catch (err) { /* private window: it just will not stick */ }
  }

  function recall() {
    try {
      return localStorage.getItem(LAST);
    } catch (err) {
      return null;
    }
  }

  function show(name) {
    if (!tabs.some((t) => t.dataset.tab === name)) name = 'routes';
    current = name;
    for (const t of tabs) t.classList.toggle('on', t.dataset.tab === name);
    for (const p of panes) p.hidden = p.dataset.pane !== name;
    $('opt-test').hidden = !TESTABLE.has(name);
    // A search carried from one tab to the next is a list that looks empty
    // for a reason you have already stopped thinking about.
    $('opt-search').value = '';
    $('opt-search').hidden = !LIST_TABS.has(name);
    editor(null);
    remember(name);
    // Each list asks the server for itself; opening a tab is when to refresh.
    if (name === 'routes') {
      if (window.refreshRoutes) window.refreshRoutes();
    } else if (name === 'gaglib') {
      if (window.refreshGaglib) window.refreshGaglib();
      if (window.refreshRules) window.refreshRules();       // your own gags
    } else if (name === 'marks') {
      if (window.refreshMarks) window.refreshMarks();
    } else if (name === 'panels') {
      if (window.renderPanels) window.renderPanels();
    } else if (RULE_TABS.has(name) || name === 'scripts') {
      if (window.refreshRules) window.refreshRules();
    }
  }

  /* Raise one editor over the panes, or `null` to go back to the list. */
  function editor(id) {
    for (const e of editors) e.hidden = e.id !== id;
    $('opt-panes').hidden = !!id;
    $('opt-test').hidden = !!id || !TESTABLE.has(current);
  }

  function setOpen(open, tab) {
    panel.hidden = !open;
    if (open) {
      show(tab || current);
      const first = panel.querySelector('.opt-pane:not([hidden]) button');
      if (first) first.focus();
    } else if (window.focusInput) {
      window.focusInput();
    }
  }

  /* What is in the search box, folded for comparing. */
  function query() {
    return $('opt-search').value.trim().toLowerCase();
  }

  /* Redraw the list that is showing, from what the browser already has --
     searching is not a reason to ask the server anything. */
  function refilter() {
    if (current === 'routes') {
      if (window.renderRoutes) window.renderRoutes();
    } else if (current === 'marks') {
      if (window.renderMarks) window.renderMarks();
    } else if (window.renderRules) {
      window.renderRules();
    }
  }

  $('opt-search').oninput = refilter;

  for (const t of tabs) t.onclick = () => show(t.dataset.tab);
  $('open-options').onclick = () => setOpen(panel.hidden);
  $('options-close').onclick = () => setOpen(false);
  // Bots is the routes tab reached in one press.  Pressing it while already
  // looking at that tab closes the panel, the way its own button does --
  // otherwise the button you opened it with does nothing on the way out.
  $('open-bots').onclick = () => {
    if (!panel.hidden && current === 'routes') setOpen(false);
    else setOpen(true, 'routes');
  };

  addEventListener('keydown', (e) => {
    if (panel.hidden) return;
    // A slash anywhere but in a field jumps to the search box, which is what
    // it does everywhere else.
    if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
        && !$('opt-search').hidden) {
      $('opt-search').focus();
      $('opt-search').select();
      e.preventDefault();
      return;
    }
    if (e.key !== 'Escape') return;
    // Escape backs out one step at a time: the search, then the editor, then
    // the panel.  Anything else and one keystroke undoes two decisions.
    const open = editors.find((el) => !el.hidden);
    if (!open && query()) {
      $('opt-search').value = '';
      refilter();
    } else if (open) {
      editor(null);
    } else {
      setOpen(false);
    }
    e.preventDefault();
  });

  /* What rules.js and routes.js use to drive the frame. */
  window.options = {
    open: (tab) => setOpen(true, tab),
    close: () => setOpen(false),
    show,
    editor,
    query,
    refilter,
    editing: () => editors.some((el) => !el.hidden),
    tab: () => current,
    /* The count beside a tab's name, so a glance says what is set up. */
    count(name, n) {
      const t = tabs.find((b) => b.dataset.tab === name);
      if (t) t.querySelector('.n').textContent = n ? String(n) : '';
    },
    /* A word beside the panel title -- what is running, mostly. */
    note(text) {
      $('opt-where').textContent = text || '';
    },
  };

  show(recall() || 'routes');

  // Both lists live on the server.  Ask once there is a socket to ask down,
  // and again after a reconnect, so the counts on the rail are true whether
  // or not anybody has opened the panel yet.
  if (window.whenConnected) {
    window.whenConnected(() => {
      if (window.refreshRoutes) window.refreshRoutes();
      if (window.refreshRules) window.refreshRules();
    });
  }
})();
