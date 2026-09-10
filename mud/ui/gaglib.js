/* Options -> Gags: your own gags, and 3kdb's a group at a time.

   Every group starts off.  A gag hides text, and a line somebody wanted to
   read going missing without their say is worse than the spam it saves them,
   so each one is a switch they throw themselves -- and they can read every
   gag in a group before they do.  Which are on belongs to the character. */

(function () {
  const $ = (id) => document.getElementById(id);
  let groups = [];
  const open = new Set();          // groups whose gags are being shown

  function send(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'gaglib', ...msg }));
    }
  }

  window.refreshGaglib = () => send({ op: 'list' });

  function render() {
    const list = $('gaglib-list');
    list.replaceChildren();
    list.dataset.empty = list.dataset.none;
    for (const g of groups) {
      const row = document.createElement('div');
      row.className = 'route' + (g.on ? ' running' : '');
      const top = document.createElement('div');
      top.className = 'top';
      const name = document.createElement('span');
      name.className = 'nm';
      name.textContent = g.title;
      const count = document.createElement('span');
      count.className = 'dist';
      count.textContent = `${g.count} gag${g.count === 1 ? '' : 's'}`;
      const show = document.createElement('button');
      show.type = 'button';
      show.textContent = open.has(g.key) ? 'Hide list' : 'Show them';
      show.onclick = () => {
        if (open.has(g.key)) open.delete(g.key); else open.add(g.key);
        render();
      };
      const toggle = document.createElement('label');
      toggle.className = 'check';
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = !!g.on;
      box.onchange = () => send({ op: 'set', key: g.key, on: box.checked });
      toggle.append(box, document.createTextNode(g.on ? 'on' : 'off'));
      top.append(name, count, show, toggle);

      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = g.what + (g.sections && g.sections.length
        ? `  ·  ${g.sections.slice(0, 12).join(', ')}` + (g.sections.length > 12 ? '…' : '')
        : '');
      row.append(top, meta);
      if (open.has(g.key)) {
        const pre = document.createElement('pre');
        pre.className = 'gag-list';
        pre.textContent = (g.gags || []).join('\n');
        row.append(pre);
      }
      list.append(row);
    }
    count();
  }

  // --- your own gags -----------------------------------------------------------
  //
  // Rules, as /gag makes them -- a trigger that hides and does nothing else --
  // listed here rather than among the triggers.  Added, switched and removed
  // through the same messages the triggers panel uses.

  let own = [];

  function rules(msg) {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'rules', ...msg }));
    }
  }

  function small(text, fn) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.onclick = fn;
    return b;
  }

  function drawOwn() {
    const list = $('gag-own');
    list.replaceChildren();
    for (const g of own) {
      const row = document.createElement('div');
      row.className = 'rule' + (g.enabled ? '' : ' off');
      const top = document.createElement('div');
      top.className = 'top';
      const pat = document.createElement('span');
      pat.className = 'pat';
      pat.textContent = g.pattern;
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = g.mode || 'contains';
      const toggle = small(g.enabled ? 'on' : 'off',
        () => rules({ op: 'save', rule: Object.assign({}, g, { enabled: !g.enabled }) }));
      if (g.enabled) toggle.classList.add('lit');
      toggle.title = g.enabled ? 'Show these lines again for now' : 'Hide them again';
      const drop = small('×', () => rules({ op: 'delete', id: g.id }));
      drop.title = 'Remove this gag';
      top.append(pat, tag, toggle, drop);
      row.append(top);
      list.append(row);
    }
    count();
  }

  window.renderOwnGags = (list) => {
    own = list || [];
    drawOwn();
  };

  $('gag-form').onsubmit = (e) => {
    e.preventDefault();
    const text = $('gag-new').value.trim();
    if (!text) return;
    if (own.some((g) => g.pattern === text && (g.mode || 'contains') === 'contains')) {
      $('gag-say').textContent = `Already hiding lines containing “${text}”.`;
      return;
    }
    rules({ op: 'save', rule: { kind: 'trigger', mode: 'contains', pattern: text,
      gag: true, actions: [], enabled: true } });
    $('gag-new').value = '';
    $('gag-say').textContent = `Hiding lines containing “${text}”.`;
  };

  function count() {
    if (window.options) {
      window.options.count('gaglib', own.length + groups.filter((g) => g.on).length);
    }
  }

  window.handleGaglib = function (m) {
    if (m.op !== 'list') return;
    groups = m.groups || [];
    render();
  };
})();
