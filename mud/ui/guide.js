/* Options -> Help: the guide, a topic at a time.

   The topics are Markdown in ui/guide/, sent by the server (guide.py), which
   also prints them for /help <topic> -- one source for both.  Only the small
   part of Markdown the guide uses is understood, and it is built into the
   page as elements, never as HTML: nothing in a topic can become markup.

   Links go three ways: [text](#topic) to another topic, [text](options:page)
   to a page of Options, and <https://...> out to your own browser. */

(function () {
  const $ = (id) => document.getElementById(id);
  let topics = [];
  let current = '';
  let asked = false;

  function ask() {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'guide' }));
      asked = true;
    }
  }

  // --- a line of text: `code`, **bold**, *italic*, links ----------------------

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function linkTo(target, label) {
    const a = el('a', '', label);
    a.href = '#';
    a.onclick = (e) => {
      e.preventDefault();
      if (target.startsWith('#')) open(target.slice(1));
      else if (target.startsWith('options:')) {
        if (window.options) window.options.open(target.slice(8));
      } else if (window.openLink) {
        window.openLink(target);
      }
    };
    return a;
  }

  const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)]+\))|(<https?:\/\/[^>]+>)|((?:^|(?<=[\s(]))\*[^*\s][^*]*\*)/g;

  function inline(text, into, marks) {
    let at = 0;
    for (const m of text.matchAll(INLINE)) {
      if (m.index > at) words(text.slice(at, m.index), into, marks);
      const got = m[0];
      if (m[1]) into.append(el('code', '', got.slice(1, -1).replace(/\\\|/g, '|')));
      else if (m[2]) { const b = el('b'); inline(got.slice(2, -2), b, marks); into.append(b); }
      else if (m[3]) {
        const [, label, target] = got.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        into.append(linkTo(target, label));
      } else if (m[4]) into.append(linkTo(got.slice(1, -1), got.slice(1, -1)));
      else { const i = el('i'); inline(got.slice(1, -1), i, marks); into.append(i); }
      at = m.index + got.length;
    }
    if (at < text.length) words(text.slice(at), into, marks);
  }

  /* Plain words, with whatever the search box asked for marked. */
  function words(text, into, marks) {
    text = text.replace(/\\\|/g, '|');
    if (!marks) { into.append(document.createTextNode(text)); return; }
    const low = text.toLowerCase();
    let at = 0;
    for (;;) {
      const hit = low.indexOf(marks, at);
      if (hit < 0) break;
      if (hit > at) into.append(document.createTextNode(text.slice(at, hit)));
      into.append(el('mark', '', text.slice(hit, hit + marks.length)));
      at = hit + marks.length;
    }
    if (at < text.length) into.append(document.createTextNode(text.slice(at)));
  }

  // --- a topic ---------------------------------------------------------------

  function cells(row) {
    return row.trim().replace(/^\|/, '').replace(/\|$/, '')
      .split(/(?<!\\)\|/).map((c) => c.trim());
  }

  function render(topic, marks) {
    const box = $('guide-article');
    box.replaceChildren();
    box.append(el('h3', '', topic.title));
    const lines = topic.body.split('\n');
    let para = [];
    let lede = true;
    const flush = () => {
      if (!para.length) return;
      const p = el('p', lede ? 'lede' : '');
      lede = false;
      inline(para.join(' '), p, marks);
      box.append(p);
      para = [];
    };
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith('```')) {
        flush();
        const code = [];
        for (i++; i < lines.length && !lines[i].startsWith('```'); i++) code.push(lines[i]);
        const pre = el('pre');
        pre.append(el('code', '', code.join('\n')));
        box.append(pre);
      } else if (line.startsWith('|')) {
        flush();
        const rows = [];
        for (; i < lines.length && lines[i].startsWith('|'); i++) rows.push(lines[i]);
        i--;
        const wrap = el('div', 'table');
        const table = el('table');
        rows.filter((r) => !/^\|[\s|:-]+\|?$/.test(r.trim())).forEach((r, n) => {
          const tr = el('tr');
          for (const c of cells(r)) {
            const td = el(n === 0 ? 'th' : 'td');
            inline(c, td, marks);
            tr.append(td);
          }
          table.append(tr);
        });
        wrap.append(table);
        box.append(wrap);
      } else if (/^(- |\d+\. )/.test(line)) {
        flush();
        const ordered = /^\d+\. /.test(line);
        const list = el(ordered ? 'ol' : 'ul');
        for (; i < lines.length && /^(- |\d+\. )/.test(lines[i]); i++) {
          const li = el('li');
          inline(lines[i].replace(/^(- |\d+\. )/, ''), li, marks);
          list.append(li);
        }
        i--;
        box.append(list);
        lede = false;
      } else if (line.startsWith('## ')) {
        flush();
        lede = false;
        box.append(el('h4', '', line.slice(3)));
      } else if (!line.trim()) {
        flush();
      } else {
        para.push(line.trim());
      }
    }
    flush();
  }

  // --- the list, and searching it ----------------------------------------------

  function query() {
    return ($('guide-find') ? $('guide-find').value : '').trim().toLowerCase();
  }

  function drawList() {
    const q = query();
    const box = $('guide-topics');
    if (!box) return;
    box.replaceChildren();
    const shown = topics.filter((t) => !q
      || (t.title + '\n' + t.body).toLowerCase().includes(q));
    for (const t of shown) {
      const b = el('button', t.id === current ? 'on' : '', t.title);
      b.type = 'button';
      b.title = t.summary || '';
      b.onclick = () => open(t.id);
      box.append(b);
    }
    if (!shown.length) box.append(el('div', 'none', 'Nothing in the help says that.'));
    // Searching shows the first topic that has it, marked.
    if (q && shown.length && !shown.some((t) => t.id === current)) show(shown[0].id);
    else if (current) show(current);
  }

  function show(id) {
    const topic = topics.find((t) => t.id === id) || topics[0];
    if (!topic) return;
    current = topic.id;
    for (const b of ($('guide-topics') ? $('guide-topics').children : [])) {
      if (b.tagName === 'BUTTON' || b.tagName === 'button') {
        b.classList.toggle('on', b.textContent === topic.title);
      }
    }
    render(topic, query());
  }

  /* Open the help at a topic, from anywhere: the rule form's "how patterns
     work", a link inside another topic. */
  function open(id) {
    if (window.options && window.options.tab && window.options.tab() !== 'guide') {
      window.options.open('guide');
    }
    current = id;
    if (topics.length) {
      show(id);
      const art = $('guide-article');
      if (art && art.scrollIntoView) art.scrollIntoView({ block: 'start' });
    }
  }

  window.guide = { open };

  window.refreshGuide = function () {
    if (!asked || !topics.length) ask();
  };

  window.handleGuide = function (m) {
    topics = m.topics || [];
    if (!current && topics.length) current = topics[0].id;
    drawList();
  };

  if ($('guide-find')) $('guide-find').oninput = drawList;

  // "How patterns work" and friends, on the forms: data-guide names the topic.
  for (const b of document.querySelectorAll ? document.querySelectorAll('[data-guide]') : []) {
    b.addEventListener('click', (e) => {
      e.preventDefault();
      open(b.dataset.guide);
    });
  }
})();
