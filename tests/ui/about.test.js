// Options -> About, told there is a newer client.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const sent = [];
const p = page({ 'about-release': 'div', 'about-check': 'button',
  'about-paths': 'div', 'about-name': 'h4', 'about-repo': 'a', version: 'div' });
const REPO = 'https://github.com/OldManDanky/dankclient';
p.els['about-repo'].href = REPO;
global.ws = { readyState: 1, send: (m) => sent.push(JSON.parse(m)) };
load('about.js');

let followed = false;
p.els['about-repo'].onclick({ preventDefault() { followed = true; } });
check('Source and releases opens in the player\'s browser too',
  followed && same(sent.splice(0), [{ t: 'open', url: REPO }]), sent);

const MSI = 'https://github.com/OldManDanky/dankclient/releases/download/v0.2.6/dankclient-0.2.6.msi';
const PAGE = 'https://github.com/OldManDanky/dankclient/releases/tag/v0.2.6';
const links = () => p.els['about-release'].children.filter((c) => c.tagName === 'a');

renderRelease({ error: '', have: '0.2.5', latest: '0.2.6', newer: true, url: MSI, page: PAGE });
const [installer, notes] = links();
check('the download link is the installer itself, not the release page',
  installer && installer.href === MSI, installer && installer.href);
check('and the release page is still there for what changed',
  notes && notes.href === PAGE && notes.textContent.includes('new'), notes && notes.href);

let stopped = false;
installer.onclick({ preventDefault() { stopped = true; } });
check('clicking hands it to the player\'s own browser, not the app window',
  stopped && same(sent, [{ t: 'open', url: MSI }]), sent);

renderRelease({ error: '', have: '0.2.5', latest: '0.2.7', newer: true, url: PAGE, page: PAGE });
check('a release with no installer attached links its page, once',
  links().length === 1 && links()[0].href === PAGE, links().map((a) => a.href));

renderRelease({ error: '', have: '0.2.5', latest: '0.2.8', newer: true,
  url: 'javascript:alert(1)', page: '' });
check('anything that is not GitHub is not a link at all',
  links().length === 1 && !links()[0].href, links()[0] && links()[0].href);

// The Session panel's version line, above uptime.
const text = (el) => (el.children && el.children.length
  ? el.children.map(text).join('') : String(el.textContent || ''));
const line = p.els.version;
renderVersion({}, '0.2.23');
check('before GitHub has answered, the version line says it is checking',
  text(line) === 'v0.2.23 · checking for updates…', text(line));
renderVersion({ error: '', have: '0.2.23', latest: '0.2.23', newer: false, checked: '14:05' }, '0.2.23');
check('the latest: up to date, and when it last asked',
  text(line) === 'v0.2.23 · up to date' && line.title.includes('14:05'), [text(line), line.title]);
renderVersion({ error: 'offline', have: '0.2.23', checked: '15:05' }, '0.2.23');
check('offline: could not check, never "up to date"',
  text(line) === 'v0.2.23 · could not check for updates', text(line));
sent.length = 0;
renderVersion({ error: '', have: '0.2.23', latest: '0.2.24', newer: true, url: MSI, page: PAGE,
  checked: '16:05' }, '0.2.23');
const download = line.children.find((c) => c.tagName === 'a');
check('a newer one: says so, with the installer to download',
  text(line) === 'v0.2.23 · 0.2.24 is out — download' && line.className === 'new'
  && download && download.href === MSI, [text(line), line.className]);
download.onclick({ preventDefault() {} });
check("download opens in the player's own browser", same(sent, [{ t: 'open', url: MSI }]), sent);

finish();
