// Options -> Colours: schemes, reading them from files, and the page's theme.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const IDS = ['ui-theme', 'scheme-list', 'scheme-import', 'scheme-file', 'scheme-error',
  'scheme-preview', 'colours-reset'];
const saved = {};
const themes = [];
let p;
function open() {
  p = page(Object.fromEntries(IDS.map((i) => [i, 'div'])), saved);
  global.setTerminalTheme = (t) => themes.push(t);
  load('colours.js');
}
const el = (id) => p.els[id];
const lastTheme = () => themes[themes.length - 1];
const row = (name) => el('scheme-list').children.find((r) => r.children[0].textContent === name);

open();
const C = window.colours;

// --- the built-in schemes ---------------------------------------------------------------
const bad = C.SCHEMES.filter((s) => !C.hex(s.background) || !C.hex(s.foreground)
  || C.ANSI.some((k) => C.hex(s[k]) !== s[k]));
check('every built-in scheme has a ground, a text colour and all sixteen', bad.length === 0,
  bad.map((s) => s.id));
check('each has its own id', new Set(C.SCHEMES.map((s) => s.id)).size === C.SCHEMES.length);
check('Dank is what the client has always looked like',
  C.SCHEMES[0].id === 'dank' && C.SCHEMES[0].background === '#111318' && C.SCHEMES[0].foreground === '#d8dde6');
check('Solarized Light knows it is light, and Dracula that it is not',
  C.SCHEMES.find((s) => s.id === 'solarized-light').light
  && !C.SCHEMES.find((s) => s.id === 'dracula').light);

// --- nothing chosen yet -------------------------------------------------------------------
check('with nothing chosen: Dank, and the page as it was',
  C.terminalTheme().background === '#111318' && p.rootStyle['--bg'] === '#111318'
  && p.rootStyle['color-scheme'] === 'dark');
check('the list offers every built-in scheme, Dank chosen',
  el('scheme-list').children.length === C.SCHEMES.length && row('Dank').className.includes('on'));
check('the preview is drawn on the scheme\'s own ground',
  el('scheme-preview').style.background === '#111318');

// --- reading a scheme from a file -------------------------------------------------------------
const WANT = { background: '#101010', foreground: '#e0e0e0', black: '#000001', red: '#aa0000',
  magenta: '#aa00aa', white: '#aaaaaa', brightBlack: '#555555', brightRed: '#ff5555',
  brightMagenta: '#ff55ff', brightWhite: '#ffffff' };
const NORMAL = ['#000001', '#aa0000', '#00aa00', '#aaaa00', '#0000aa', '#aa00aa', '#00aaaa', '#aaaaaa'];
const BRIGHT = ['#555555', '#ff5555', '#55ff55', '#ffff55', '#5555ff', '#ff55ff', '#55ffff', '#ffffff'];
const NAMES = ['black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'];
const matches = (got) => got.scheme && Object.entries(WANT).every(([k, v]) => got.scheme[k] === v);

const alacritty = "[colors.primary]\nbackground = '#101010'\nforeground = \"#E0E0E0\"\n\n"
  + '[colors.normal]\n' + NAMES.map((n, i) => `${n} = '${NORMAL[i]}'`).join('\n') + '\n\n'
  + '[colors.bright]\n' + NAMES.map((n, i) => `${n} = '${i === 0 ? '0x555555' : BRIGHT[i]}'`).join('\n') + '\n';
check('Alacritty (.toml)', matches(C.parse(alacritty, 'test-scheme.toml')), C.parse(alacritty, 'x'));

const comp = (h) => ['Red', 'Green', 'Blue'].map((c, i) =>
  `<key>${c} Component</key><real>${parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16) / 255}</real>`).join('');
const entry = (name, h) => `<key>${name}</key>\n<dict><key>Color Space</key><string>sRGB</string>${comp(h)}</dict>`;
const iterm = '<?xml version="1.0"?><plist version="1.0"><dict>'
  + [...NORMAL, ...BRIGHT].map((h, i) => entry(`Ansi ${i} Color`, h)).join('\n')
  + entry('Background Color', '#101010') + entry('Foreground Color', '#e0e0e0') + '</dict></plist>';
check('iTerm2 (.itermcolors)', matches(C.parse(iterm, 'Test.itermcolors')), C.parse(iterm, 'x'));

const ghostty = [...NORMAL, ...BRIGHT].map((h, i) => `palette = ${i}=${h}`).join('\n')
  + '\nbackground = 101010\nforeground = e0e0e0\n';
check('Ghostty', matches(C.parse(ghostty, 'test')), C.parse(ghostty, 'x'));

const wt = { name: 'Test Scheme', background: '#101010', foreground: '#E0E0E0' };
NAMES.forEach((n, i) => {
  const key = n === 'magenta' ? 'purple' : n;
  wt[key] = NORMAL[i];
  wt['bright' + key[0].toUpperCase() + key.slice(1)] = BRIGHT[i];
});
const wtGot = C.parse(JSON.stringify(wt), 'whatever.json');
check('Windows Terminal (.json), purple and all', matches(wtGot) && wtGot.scheme.name === 'Test Scheme', wtGot);

const xres = '! a comment\n*.background: #101010\n*.foreground: #e0e0e0\n'
  + [...NORMAL, ...BRIGHT].map((h, i) => `*.color${i}: ${h}`).join('\n');
check('Xresources', matches(C.parse(xres, 'test.Xresources')), C.parse(xres, 'x'));

check('the name comes from the file when the file does not say',
  C.parse(alacritty, 'rose-pine_moon.toml').scheme.name === 'rose pine moon');
check('something that is not a scheme says so',
  C.parse('hello there', 'notes.txt').error === 'that is not a colour scheme this client can read');
const noBlue = alacritty.replace(/^blue = .*$/m, '');
check('a scheme missing a colour says which',
  (C.parse(noBlue, 'x.toml').error || '').includes('blue'), C.parse(noBlue, 'x.toml'));

// --- choosing ----------------------------------------------------------------------------------
row('Dracula').onclick();
check('choosing one sends it to the terminal and remembers it',
  saved['colours:terminal'] === 'dracula' && lastTheme().background === '#282a36'
  && lastTheme().red === '#ff5555' && row('Dracula').className.includes('on'));
check('the cursor is the ground: the terminal takes no input',
  lastTheme().cursor === '#282a36' && lastTheme().cursorAccent === '#282a36');

check('adding one from a file chooses it', C.addScheme(alacritty, 'Test Scheme.toml') === ''
  && lastTheme().background === '#101010' && row('Test Scheme') && JSON.parse(saved['colours:own']).length === 1);
check('a file that is not one leaves everything as it was',
  C.addScheme('nope', 'x.txt') !== '' && lastTheme().background === '#101010');
open();
check('it is still there next time', row('Test Scheme') && C.chosen().name === 'Test Scheme');
row('Test Scheme').children.find((c) => c.textContent === '×').onclick({ stopPropagation() {} });
check('removing the chosen one goes back to Dank',
  !row('Test Scheme') && saved['colours:terminal'] === 'dank' && lastTheme().background === '#111318');

// --- the page's theme ------------------------------------------------------------------------
el('ui-theme').value = 'light';
el('ui-theme').onchange();
check('Light', p.rootStyle['--bg'] === '#f5f6f8' && p.rootStyle['color-scheme'] === 'light'
  && saved['colours:ui'] === 'light');
row('Solarized Light').onclick();
el('ui-theme').value = 'match';
el('ui-theme').onchange();
check('Match the terminal takes the page from the scheme',
  p.rootStyle['--bg'] === '#fdf6e3' && p.rootStyle['--ink'] === '#657b83'
  && p.rootStyle['--bad'] === '#dc322f' && p.rootStyle['color-scheme'] === 'light', p.rootStyle);
row('Dracula').onclick();
check('and follows it when the scheme changes', p.rootStyle['--bg'] === '#282a36'
  && p.rootStyle['color-scheme'] === 'dark');
el('colours-reset').onclick();
check('back to the defaults: Dank, Dark', saved['colours:terminal'] === 'dank'
  && saved['colours:ui'] === 'dark' && p.rootStyle['--bg'] === '#111318');

finish();
