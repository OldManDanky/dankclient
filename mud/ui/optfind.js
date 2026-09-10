/* Find a setting: type what you are looking for, and go to it.

   Options has fifteen pages.  Somebody who wants the numpad should not have
   to know it lives under Keyboard, so the box at the top of the rail searches
   every page -- their titles, the boxes on them, each setting's name and its
   hint -- and lists what matches in the pane area.  Choosing one opens its
   page and marks it.

   It reads the pages as they are when you type rather than a list kept here,
   so a setting added to the page is findable without anybody remembering to
   add it to a list as well. */

(function () {
  const $ = (id) => document.getElementById(id);
  const box = $('opt-find');
  const out = $('opt-results');
  if (!box || !out) return;
  const MOST = 30;

  const text = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '');

  function pageName(tab) {
    const b = document.querySelector(`#opt-tabs button[data-tab="${tab}"]`);
    if (!b) return tab;
    const n = b.querySelector('.n');
    return text(b).slice(0, text(b).length - (n ? text(n).length : 0)).trim();
  }

  /* Everything findable, in page order. */
  function items() {
    const found = [];
    for (const pane of document.querySelectorAll('.opt-pane')) {
      const tab = pane.dataset.pane;
      const page = pageName(tab);
      found.push({ tab, el: pane, label: page, where: 'Page',
        hay: `${page} ${text(pane.querySelector('.opt-head p'))}` });
      for (const set of pane.querySelectorAll('.fset')) {
        const section = text(set.querySelector('h5'));
        const say = [...set.querySelectorAll('.say')].map(text).join(' ');
        found.push({ tab, el: set, label: section, where: page,
          hay: `${section} ${page} ${say}` });
        for (const row of set.querySelectorAll('.frow')) {
          if (row.hidden) continue;
          const first = row.firstElementChild;
          const own = first && first.tagName === 'LABEL' ? text(first) : '';
          const checks = [...row.querySelectorAll('label.check')].map(text);
          const label = own || checks[0] || '';
          if (!label) continue;
          const options = [...row.querySelectorAll('option')].map(text).join(' ');
          found.push({ tab, el: row, label, where: `${page} › ${section}`,
            hay: `${label} ${checks.join(' ')} ${options} ${section} ${page} `
              + text(row.querySelector('.fhint')) });
        }
        for (const b of set.querySelectorAll('button')) {
          if (b.closest('.frow') || text(b).length < 3) continue;
          found.push({ tab, el: b, label: text(b), where: `${page} › ${section}`,
            hay: `${text(b)} ${b.title || ''} ${section} ${page}` });
        }
      }
    }
    return found;
  }

  /* Names first, then anything whose hint or page matches. */
  function search(q) {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const has = (s) => words.every((w) => s.toLowerCase().includes(w));
    const hits = [];
    items().forEach((item, order) => {
      if (has(item.label)) hits.push({ item, score: 2, order });
      else if (has(item.hay)) hits.push({ item, score: 1, order });
    });
    return hits.sort((a, b) => b.score - a.score || a.order - b.order)
      .map((h) => h.item);
  }

  function restore() {
    out.hidden = true;
    out.replaceChildren();
    if (window.options) window.options.show(window.options.tab());
  }

  function go(item) {
    box.value = '';
    restore();
    if (window.options) window.options.show(item.tab);
    requestAnimationFrame(() => {
      item.el.scrollIntoView({ block: 'center' });
      item.el.classList.remove('opt-flash');
      void item.el.offsetWidth;                 // restart the mark if repeated
      item.el.classList.add('opt-flash');
      setTimeout(() => item.el.classList.remove('opt-flash'), 1700);
      const ctl = item.el.matches('input, select, textarea, button') ? item.el
        : item.el.querySelector('input, select, textarea');
      if (ctl) ctl.focus({ preventScroll: true });
    });
  }

  function draw(q) {
    if (window.options && window.options.editing()) window.options.editor(null);
    $('opt-panes').hidden = true;
    $('opt-test').hidden = true;
    out.hidden = false;
    out.replaceChildren();
    const head = document.createElement('h4');
    head.textContent = `Settings matching “${q}”`;
    out.append(head);
    const hits = search(q);
    if (!hits.length) {
      const none = document.createElement('p');
      none.className = 'none';
      none.textContent = 'Nothing matches. Try another word — a setting’s name, '
        + 'or what it does.';
      out.append(none);
      return;
    }
    for (const item of hits.slice(0, MOST)) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'opt-hit';
      const name = document.createElement('b');
      name.textContent = item.label;
      const where = document.createElement('span');
      where.textContent = item.where;
      b.append(name, where);
      b.onclick = () => go(item);
      out.append(b);
    }
  }

  box.oninput = () => {
    const q = box.value.trim();
    if (q) draw(q);
    else restore();
  };
  box.onkeydown = (e) => {
    if (e.key === 'Escape' && box.value) {
      // One step back: the search, not the whole panel.
      e.preventDefault();
      e.stopPropagation();
      box.value = '';
      restore();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const first = box.value.trim() && search(box.value.trim())[0];
      if (first) go(first);
    }
  };
  // Choosing a page from the rail ends the search.
  $('opt-tabs').addEventListener('click', (e) => {
    if (box.value && e.target.closest && e.target.closest('button[data-tab]')) {
      box.value = '';
      out.hidden = true;
      out.replaceChildren();
    }
  }, true);
})();
