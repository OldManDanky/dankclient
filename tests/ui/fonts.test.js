// Options -> Fonts, run for real against a canvas that "has" three fonts.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const INSTALLED = { 'Consolas': 'mono', 'Cascadia Mono': 'mono', 'Comic Sans MS': 'prop' };
function measure(font, text) {
  const m = font.match(/^40px (?:"([^"]+)", )?(\S+)$/);
  const name = m && m[1];
  const base = m ? m[2] : 'monospace';
  const kind = name && INSTALLED[name];
  if (kind === 'mono') return text.length * (name.length + 20);
  if (kind === 'prop') return [...text].reduce((w, ch) => w + (ch === 'i' || ch === 'l' ? 8 : 30), 0);
  return text.length * ({ monospace: 24, serif: 19, 'sans-serif': 21 }[base] || 24);
}
const pen = { font: '' };
pen.measureText = (t) => ({ width: measure(pen.font, t) });
global.__pen = pen;

const saved = {};
const calls = [];
const IDS = ['font-family', 'font-other-row', 'font-other', 'font-other-hint', 'font-size',
  'font-line', 'font-msg', 'font-preview', 'font-reset'];
let p;
function open() {
  p = page(Object.fromEntries(IDS.map((i) => [i, 'div'])), saved);
  p.els['font-other-row'].hidden = true;
  global.fontStack = (n) => (n ? `"${n}", ` : '') + 'Consolas, "DejaVu Sans Mono", monospace';
  global.setTerminalFont = (family, size, line) => calls.push([family, size, line]);
  load('fonts.js');
}
const el = (id) => p.els[id];
const enter = () => el('font-other').onkeydown({ key: 'Enter', preventDefault() {} });

open();
const offered = el('font-family').children.map((o) => o.textContent);
check('offers Default, the installed fixed-width fonts, and Other',
  same(offered, ['Default (Consolas)', 'Consolas', 'Cascadia Mono', 'Other…']), offered);
check('applied at load, to the terminal and the page',
  calls.length === 1 && p.rootStyle['--term-size'] === '14px' && p.rootStyle['--cm-size'] === '11px');
el('font-family').value = 'Cascadia Mono'; el('font-family').onchange();
el('font-size').value = '18'; el('font-size').onchange();
el('font-line').value = '1.2'; el('font-line').onchange();
el('font-msg').value = '13'; el('font-msg').onchange();
check('a choice reaches the terminal', same(calls[calls.length - 1], ['Cascadia Mono', 18, 1.2]), calls[calls.length - 1]);
check('and the command box and messages', p.rootStyle['--term-font'].startsWith('"Cascadia Mono"')
  && p.rootStyle['--term-size'] === '18px' && p.rootStyle['--cm-size'] === '13px');
check('and is saved', saved['font:family'] === 'Cascadia Mono' && saved['font:size'] === '18');
check('the preview follows', el('font-preview').style.fontSize === '18px');
el('font-family').value = '__other__'; el('font-family').onchange();
check('Other opens a box for a name', el('font-other-row').hidden === false);
const before = calls.length;
el('font-other').value = 'Nope Mono'; enter();
check('a font that is not installed is refused, with a reason',
  calls.length === before && el('font-other-hint').classList.contains('warn'));
el('font-other').value = 'Comic Sans MS'; enter();
check('a proportional font is taken, with a warning',
  saved['font:family'] === 'Comic Sans MS' && el('font-other-hint').textContent.includes('not fixed-width'));
el('font-other').value = 'x"; } body { display:none'; enter();
check('a name that would break out of the CSS never gets in',
  !String(saved['font:family']).includes('"') && !String(saved['font:family']).includes('}'));
el('font-reset').onclick();
check('Back to the defaults', saved['font:family'] === '' && same(calls[calls.length - 1], ['', 14, 1]));
saved['font:size'] = '20';
calls.length = 0;
open();
check('a reload starts in the saved choice', same(calls[0], ['', 20, 1]), calls[0]);

finish();
