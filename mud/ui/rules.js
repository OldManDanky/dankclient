/* The rule tabs of the options panel: triggers, aliases, events, watches.

   Rules are data on the server; this only edits them.  They register into the
   same engine script files use, so there is one place where matching happens.
   "Show as Python" renders the equivalent script -- the second door, for
   anyone who outgrows the form.

   One editor serves all four kinds.  Which kind you are making is decided by
   the tab you started from rather than by a dropdown inside the form: the tab
   already says it, and asking twice is how a form starts to feel like a
   questionnaire. */

(function () {
  const $ = (id) => document.getElementById(id);
  let editing = null;        // the rule being edited, or null
  let cache = { rules: [], scripts: [], paces: [], events: {},
                watch_fields: [], ops: [], context_fields: [] };

  function rq(op, extra) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify(Object.assign({ t: 'rules', op }, extra || {})));
    }
  }

  //: opening a rule tab is when to ask the server for the current set
  window.refreshRules = () => rq('list');

  /* Everything about a rule that somebody might search for.

     Its actions included: half of what you remember about a rule is what it
     does, not what sets it off -- "the one that quaffs" is a search for the
     command, and the pattern that fires it is the part you have forgotten. */
  function haystack(r) {
    return [
      r.name, r.pattern, r.mode, r.kind, r.event, r.watch_field, r.value,
      r.kind === 'timer' ? `every ${r.every}s` : '',
      ...(r.actions || []).map((a) => a.text),
      ...(r.conditions || []).map((c) => `${c.field} ${c.value}`),
    ].filter(Boolean).join(' \u0000 ').toLowerCase();
  }

  function matches(r) {
    const q = window.options ? window.options.query() : '';
    if (!q) return true;
    // Every word, anywhere: "quaff heal" finds it whichever order you
    // remember them in.
    const hay = haystack(r);
    return q.split(/\s+/).every((word) => hay.includes(word));
  }

  const KINDS = ['trigger', 'alias', 'event', 'watch', 'timer'];
  const LIST = { trigger: 'list-trigger', alias: 'list-alias',
                 event: 'list-event', watch: 'list-watch',
                 timer: 'list-timer' };

  // --- test box -------------------------------------------------------------

  $('rule-test-form').onsubmit = (e) => {
    e.preventDefault();
    const line = $('rule-test').value;
    if (line) rq('test', { line });
  };

  // --- action rows ----------------------------------------------------------

  function actionRow(action) {
    const row = document.createElement('div');
    row.className = 'action-row';

    const type = document.createElement('select');
    for (const t of ['send', 'log']) {
      const o = document.createElement('option');
      o.value = t;
      o.textContent = t === 'send' ? 'send to MUD' : 'show in client';
      type.append(o);
    }
    type.value = (action && action.type) || 'send';

    const text = document.createElement('input');
    text.type = 'text';
    text.spellcheck = false;
    text.placeholder = 'command, {name} inserts a capture';
    text.value = (action && action.text) || '';

    const del = document.createElement('button');
    del.type = 'button';
    del.textContent = '×';
    del.onclick = () => row.remove();

    row.append(type, text, del);
    return row;
  }

  $('f-add-action').onclick = () => $('f-actions').append(actionRow());

  function fillSelect(el, options, selected) {
    el.replaceChildren();
    for (const o of options) {
      const opt = document.createElement('option');
      opt.value = typeof o === 'string' ? o : o.value;
      opt.textContent = typeof o === 'string' ? o : o.label;
      el.append(opt);
    }
    if (selected !== undefined && selected !== null) el.value = selected;
  }

  function fillGrouped(el, groups, selected) {
    el.replaceChildren();
    for (const [label, options] of groups) {
      if (!options.length) continue;
      const g = document.createElement('optgroup');
      g.label = label;
      for (const o of options) {
        const opt = document.createElement('option');
        opt.value = o;
        opt.textContent = o;
        g.append(opt);
      }
      el.append(g);
    }
    if (selected) el.value = selected;
  }

  // Conditions may test the event's own fields *or* anything MIP is already
  // tracking -- "on a round, only when enemy_pct < 20" is the obvious case,
  // and the round event carries only {round} of its own.
  function conditionFields() {
    const own = cache.events[$('f-event').value] || [];
    const extra = cache.context_fields.filter((f) => !own.includes(f));
    return [['from the event', own], ['current state', extra]];
  }

  function conditionRow(cond) {
    const row = document.createElement('div');
    row.className = 'action-row';

    const field = document.createElement('select');
    fillGrouped(field, conditionFields(), cond && cond.field);

    const op = document.createElement('select');
    fillSelect(op, cache.ops, (cond && cond.op) || 'contains');

    const value = document.createElement('input');
    value.type = 'text';
    value.spellcheck = false;
    value.value = (cond && cond.value) || '';

    const del = document.createElement('button');
    del.type = 'button';
    del.textContent = '×';
    del.onclick = () => row.remove();

    row.append(field, op, value, del);
    return row;
  }

  $('f-add-cond').onclick = () => $('f-conditions').append(conditionRow());

  // --- form -----------------------------------------------------------------

  function showForm(rule, kind) {
    editing = rule || null;
    if (window.options) window.options.editor('rule-editor');
    $('f-code').hidden = true;
    $('f-error').textContent = '';
    $('rule-form-title').textContent = rule ? 'Edit rule' : 'New rule';
    $('f-name').value = (rule && rule.name) || '';
    $('f-kind').value = (rule && rule.kind) || kind || 'trigger';
    $('f-mode').value = (rule && rule.mode)
      || ((kind || (rule && rule.kind)) === 'alias' ? 'command' : 'contains');
    $('f-pattern').value = (rule && rule.pattern) || '';
    $('f-enabled').checked = rule ? !!rule.enabled : true;
    $('f-stop').checked = rule ? !!rule.stop : false;
    $('f-actions').replaceChildren();
    const actions = (rule && rule.actions && rule.actions.length)
      ? rule.actions : [{ type: 'send', text: '' }];
    for (const a of actions) $('f-actions').append(actionRow(a));
    fillSelect($('f-event'), Object.keys(cache.events),
               (rule && rule.event) || 'tell');
    fillSelect($('f-watch-field'), cache.watch_fields,
               (rule && rule.watch_field) || 'hp_pct');
    fillSelect($('f-op'), cache.ops, (rule && rule.op) || 'lt');
    $('f-value').value = (rule && rule.value) || '';
    $('f-every').value = rule && rule.every ? String(rule.every) : '290';
    $('f-edge').checked = rule ? rule.edge !== false : true;
    fillPaces(rule && rule.pace);
    hint();
    kindHint();
    $('f-conditions').replaceChildren();
    for (const c of (rule && rule.conditions) || []) {
      $('f-conditions').append(conditionRow(c));
    }
    const kinds = { trigger: 'f-pattern', alias: 'f-pattern',
                    event: 'f-event', watch: 'f-value', timer: 'f-every' };
    $(kinds[$('f-kind').value] || 'f-pattern').focus();
  }

  const PACE_HINTS = {
    now: 'Sends the moment it matches, even if the minute is busy.',
    paced: 'Sends at once, but holds back as you approach the APM limit.',
    round: 'At most one per 2s combat round. For attack rotations.',
  };

  function paceHint() {
    $('f-pace-hint').textContent = PACE_HINTS[$('f-pace').value] || '';
  }
  $('f-pace').onchange = paceHint;

  function fillPaces(selected) {
    const sel = $('f-pace');
    sel.replaceChildren();
    const opts = cache.paces.length ? cache.paces
      : [{ value: 'paced', label: 'normal' }];
    for (const p of opts) {
      const o = document.createElement('option');
      o.value = p.value;
      o.textContent = p.label;
      sel.append(o);
    }
    sel.value = selected || 'paced';
    paceHint();
  }

  const KIND_TITLE = {
    trigger: 'trigger', alias: 'alias', event: 'MIP event rule',
    watch: 'stat watch', timer: 'timer',
  };

  function kindHint() {
    const kind = $('f-kind').value;
    $('rule-form-title').textContent =
      (editing ? 'Edit ' : 'New ') + (KIND_TITLE[kind] || kind);
    $('grp-text').hidden = !(kind === 'trigger' || kind === 'alias');
    $('grp-event').hidden = kind !== 'event';
    $('grp-watch').hidden = kind !== 'watch';
    $('grp-timer').hidden = kind !== 'timer';
    $('f-pattern').placeholder = kind === 'alias'
      ? 'the word you type, e.g.  gk'
      : 'text the MUD sends, e.g.  dealt the killing blow to';
    if (kind === 'event') eventHint();
    if (kind === 'watch') {
      $('f-watch-fields').textContent = cache.context_fields.length
        ? 'Use in actions: ' + cache.context_fields.map((f) => `{${f}}`).join(' ')
        : '';
    }
  }
  $('f-kind').onchange = kindHint;

  function eventHint() {
    const own = cache.events[$('f-event').value] || [];
    // context is available whatever fired the rule, so a tell rule can report
    // your health and a round rule can name the target
    const extra = cache.context_fields.filter((f) => !own.includes(f));
    $('f-event-fields').textContent =
      (own.length ? 'From the event: ' + own.map((f) => `{${f}}`).join(' ') : '')
      + (extra.length ? '\nAlso available: ' + extra.map((f) => `{${f}}`).join(' ') : '');
    // Rebuild each condition's field list for the new event, keeping the
    // chosen field where it still exists rather than discarding the row.
    for (const row of $('f-conditions').querySelectorAll('.action-row')) {
      const sel = row.querySelector('select');
      const keep = sel.value;
      fillGrouped(sel, conditionFields(), keep);
      if (sel.value !== keep) sel.selectedIndex = 0;
    }
  }
  $('f-event').onchange = eventHint;

  function hint() {
    const mode = $('f-mode').value;
    $('f-hint').textContent = {
      command: 'Exact first word. Anything after it is {args}, and single '
             + 'words are {1}, {2}. Best for aliases.',
      contains: 'Matches if the line contains this text. Simplest and fastest.',
      glob: 'Use * for "anything", e.g.  * tells you: *',
      regex: 'Full regex. Named groups (?P<who>\\w+) become {who} in actions.',
    }[mode];
  }
  $('f-mode').onchange = hint;

  function collect() {
    const actions = [...$('f-actions').querySelectorAll('.action-row')].map((r) => ({
      type: r.querySelector('select').value,
      text: r.querySelector('input').value,
    })).filter((a) => a.text.trim());
    return {
      id: editing ? editing.id : '',
      name: $('f-name').value,
      kind: $('f-kind').value,
      mode: $('f-mode').value,
      pattern: $('f-pattern').value,
      enabled: $('f-enabled').checked,
      stop: $('f-stop').checked,
      priority: editing ? editing.priority : 0,
      pace: $('f-pace').value,
      event: $('f-event').value,
      watch_field: $('f-watch-field').value,
      op: $('f-op').value,
      value: $('f-value').value,
      every: parseFloat($('f-every').value) || 0,
      edge: $('f-edge').checked,
      conditions: [...$('f-conditions').querySelectorAll('.action-row')].map((r) => ({
        field: r.querySelectorAll('select')[0].value,
        op: r.querySelectorAll('select')[1].value,
        value: r.querySelector('input').value,
      })).filter((c) => c.value.trim()),
      actions,
    };
  }

  for (const [id, kind] of [['rule-new-trigger', 'trigger'],
                            ['rule-new-alias', 'alias'],
                            ['rule-new-event', 'event'],
                            ['rule-new-watch', 'watch'],
                            ['rule-new-timer', 'timer']]) {
    const b = $(id);
    if (b) b.onclick = () => showForm(null, kind);
  }
  function closeForm() {
    if (window.options) window.options.editor(null);
    editing = null;
  }
  $('f-cancel').onclick = closeForm;
  $('f-back').onclick = closeForm;
  $('f-python').onclick = () => rq('python', { rule: collect() });
  $('rule-form').onsubmit = (e) => {
    e.preventDefault();
    rq('save', { rule: collect() });
  };

  // --- rendering ------------------------------------------------------------

  function render() {
    const q = window.options ? window.options.query() : '';
    for (const kind of KINDS) {
      const list = $(LIST[kind]);
      list.replaceChildren();
      const mine = cache.rules.filter((r) => (r.kind || 'trigger') === kind);
      const shown = mine.filter(matches);
      // The tab counts stay the totals: they are what you have, and a search
      // is a way of looking at it rather than a change to it.
      if (window.options) window.options.count(kind, mine.length);
      list.dataset.empty = q
        ? `Nothing here matches “${q}”.`
        : list.dataset.none || 'Nothing here yet.';
      for (const r of shown) list.append(card(r));
    }
    if (window.options) window.options.count('scripts', cache.scripts.length);
    renderScripts();
  }

  //: redraw from what we already have -- searching asks the server nothing
  window.renderRules = render;

  function card(r) {
    const el = document.createElement('div');
    el.className = 'rule' + (r.enabled ? '' : ' off');

    const opLabel = (cache.ops.find((o) => o.value === r.op) || {}).label || r.op;
    // What this rule watches for, said the way the tab it lives on would.
    const what = r.kind === 'event' ? `on ${r.event}`
      : r.kind === 'watch' ? `${r.watch_field} ${opLabel} ${r.value}`
      : r.kind === 'timer' ? `every ${r.every}s`
      : r.pattern;

    const top = document.createElement('div');
    top.className = 'top';

    const tag = document.createElement('span');
    tag.className = 'tag' + (r.kind === 'alias' ? ' alias' : '');
    tag.textContent = r.mode && (r.kind === 'trigger' || r.kind === 'alias')
      ? r.mode : r.kind;

    const pat = document.createElement('span');
    pat.className = 'pat';
    pat.textContent = r.name ? `${r.name} — ${what}` : what;
    pat.title = what;

    const acts = document.createElement('span');
    acts.className = 'acts';
    const toggle = button(r.enabled ? 'on' : 'off', () =>
      rq('save', { rule: Object.assign({}, r, { enabled: !r.enabled }) }));
    toggle.title = r.enabled ? 'Switch it off' : 'Switch it on';
    if (r.enabled) toggle.classList.add('lit');
    acts.append(toggle,
                button('edit', () => showForm(r)),
                button('delete', () => {
                  if (confirm(`Delete ${r.name || what}?`)) rq('delete', { id: r.id });
                }));

    top.append(tag, pat, acts);

    const meta = document.createElement('div');
    meta.className = 'meta';
    const paceLabel = (cache.paces.find((p) => p.value === r.pace) || {}).label;
    const how = r.kind === 'event'
      ? (r.conditions || []).map((c) => `${c.field} ${c.op} "${c.value}"`)
          .join(' and ') || 'whenever it happens'
      : r.kind === 'watch' ? (r.edge === false ? 'every update' : 'on crossing')
      : '';
    meta.textContent = [
      how,
      r.pace && r.pace !== 'paced' ? paceLabel || r.pace : '',
      r.actions.map((a) => (a.type === 'log' ? 'show' : 'send') + ` "${a.text}"`)
        .join(' · '),
    ].filter(Boolean).join('  ·  ');

    el.append(top, meta);
    return el;
  }

  function button(text, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.onclick = fn;
    return b;
  }

  function renderScripts() {
    const q = window.options ? window.options.query() : '';
    const fromScripts = $('rule-scripts');
    fromScripts.replaceChildren();
    fromScripts.dataset.empty = q
      ? `No script rule matches “${q}”.`
      : fromScripts.dataset.none || 'No script files loaded.';
    const hit = (t) => !q || q.split(/\s+/).every((word) =>
      `${t.owner} ${t.pattern} ${t.mode}`.toLowerCase().includes(word));
    for (const t of cache.scripts.filter(hit)) {
      const el = document.createElement('div');
      el.className = 'rule';
      const top = document.createElement('div');
      top.className = 'top';
      const tag = document.createElement('span');
      tag.className = 'tag' + (t.kind === 'alias' ? ' alias' : '');
      tag.textContent = t.owner;
      const pat = document.createElement('span');
      pat.className = 'pat';
      pat.textContent = t.pattern;
      pat.title = t.pattern;
      top.append(tag, pat);
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = t.literal
        ? `${t.mode} · prefilter "${t.literal}"`
        : `${t.mode} · checked on every line`;
      el.append(top, meta);
      fromScripts.append(el);
    }
  }

  // --- messages from the server --------------------------------------------

  window.handleRules = function (m) {
    if (m.op === 'list') {
      cache = { rules: m.rules || [], scripts: m.scripts || [],
                paces: m.paces || [], events: m.events || {},
                watch_fields: m.watch_fields || [], ops: m.ops || [],
                context_fields: m.context_fields || [] };
      closeForm();
      render();
    } else if (m.op === 'error') {
      $('f-error').textContent = m.error;
    } else if (m.op === 'python') {
      $('f-code').hidden = false;
      $('f-code').value = m.code;
    } else if (m.op === 'tested') {
      const out = $('rule-test-out');
      out.replaceChildren();
      if (!m.hits.length) {
        out.textContent = 'nothing matched (tried triggers and aliases)';
        return;
      }
      for (const h of m.hits) {
        const line = document.createElement('div');
        line.className = 'hit';
        const caps = Object.entries(h.captured || {})
          .map(([k, v]) => `${k}=${v}`).join(' ');
        line.textContent = `${h.kind || 'trigger'} [${h.owner}] ${h.pattern}`
          + (caps ? `  ${caps}` : '');
        out.append(line);
      }
    }
  };
})();
