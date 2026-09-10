/* A stand-in page: just enough of the DOM for the client's UI scripts to run
   under Node, so their real logic is exercised rather than their text read.

   No browser, no jsdom -- the project takes no dependencies, and Node is only
   ever optional: tests/run.py runs these when it is there and says so when it
   is not.  Each *.test.js builds the elements its script looks up, loads the
   real file from mud/ui, and drives it the way a browser would.  What this
   cannot see is how anything looks. */

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');

class El {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.parent = null;
    this.className = '';
    this.textContent = '';
    this.title = '';
    this.value = '';
    this.checked = false;
    this.hidden = false;
    this.attrs = {};
    this.dataset = {};
    this.scrollHeight = 0;
    this.scrollTop = 0;
    this.clientHeight = 0;
    this.selectionStart = 0;
    this.selectionEnd = 0;
    const style = {};
    style.setProperty = (k, v) => { style[k] = v; };
    this.style = style;
  }

  get classList() {
    const el = this;
    const set = () => new Set(el.className.split(' ').filter(Boolean));
    const put = (s) => { el.className = [...s].join(' '); };
    return {
      contains: (c) => set().has(c),
      add: (c) => { const s = set(); s.add(c); put(s); },
      remove: (c) => { const s = set(); s.delete(c); put(s); },
      toggle: (c, on) => {
        const s = set();
        const want = on === undefined ? !s.has(c) : on;
        if (want) s.add(c); else s.delete(c);
        put(s);
        return want;
      },
    };
  }

  append(...kids) {
    for (const k of kids) { k.parent = this; this.children.push(k); }
  }

  replaceChildren(...kids) { this.children = []; this.append(...kids); }

  remove() {
    if (this.parent) {
      this.parent.children = this.parent.children.filter((c) => c !== this);
      this.parent = null;
    }
  }

  querySelectorAll(sel) {
    const want = sel.startsWith('.')
      ? (e) => e.className.split(' ').includes(sel.slice(1))
      : (e) => e.tagName === sel;
    const out = [];
    const walk = (e) => { for (const c of e.children) { if (want(c)) out.push(c); walk(c); } };
    walk(this);
    return out;
  }

  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }

  contains(x) {
    for (let e = x; e; e = e.parent) if (e === this) return true;
    return false;
  }

  closest() { return null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
  removeEventListener() {}
  focus() { this.focused = true; }
  getBoundingClientRect() { return { width: 200, height: 120 }; }
  getContext() { return global.__pen || null; }
}

/* A page with these ids, and preferences in `saved` (kept across reloads by
   passing the same object again). */
function page(ids = {}, saved = {}) {
  const els = {};
  for (const [id, tag] of Object.entries(ids)) els[id] = new El(tag || 'div');
  const listeners = {};
  const rootStyle = {};
  global.window = global;
  global.innerWidth = 1000;
  global.innerHeight = 800;
  global.addEventListener = () => {};
  global.removeEventListener = () => {};
  global.document = {
    body: new El('body'),
    hidden: false,
    hasFocus: () => true,
    createElement: (t) => new El(t),
    getElementById: (id) => els[id] || null,
    documentElement: { style: { setProperty: (k, v) => { rootStyle[k] = v; } } },
    addEventListener: (t, f) => { (listeners[t] = listeners[t] || new Set()).add(f); },
    removeEventListener: (t, f) => { if (listeners[t]) listeners[t].delete(f); },
  };
  global.prefs = {
    get: (k, f) => (k in saved ? saved[k] : f),
    set: (k, v) => { saved[k] = v; },
  };
  return { els, saved, listeners, rootStyle };
}

/* The messages window's own markup, as index.html has it. */
function messagesWindow() {
  const root = new El('div');
  for (const [tag, cls] of [['header', ''], ['div', 'cm-body'], ['div', 'cm-filters'],
    ['span', 'cm-count'], ['span', 'cm-toggle']]) {
    const e = new El(tag);
    e.className = cls;
    root.append(e);
  }
  return root;
}

/* Run one of the client's own scripts, in the global scope as a page would. */
function load(file) {
  (0, eval)(fs.readFileSync(path.join(ROOT, 'mud', 'ui', file), 'utf8'));
}

const results = [];

function check(label, ok, got) {
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}`
    + (ok || got === undefined ? '' : `  -> ${JSON.stringify(got)}`));
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function finish() {
  console.log(results.join('\n'));
  if (results.some((r) => r.startsWith('FAIL'))) process.exitCode = 1;
}

module.exports = { El, page, messagesWindow, load, check, same, finish };
