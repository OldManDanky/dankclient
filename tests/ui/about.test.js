// Options -> About, told there is a newer client.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const sent = [];
const p = page({ 'about-release': 'div', 'about-check': 'button',
  'about-paths': 'div', 'about-name': 'h4', 'about-repo': 'a' });
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

finish();
