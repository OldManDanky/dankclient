// The Bot panel: find a route, start, pause, resume, stop.
'use strict';

const { page, load, check, same, finish } = require('./stage');

const sent = [];
const IDS = ['bot-now', 'bot-name', 'bot-step', 'bot-bar', 'bot-note', 'bot-start',
  'bot-pause', 'bot-stop', 'bot-find', 'bot-found'];
const saved = {};
const p = page(Object.fromEntries(IDS.map((i) => [i, i === 'bot-find' ? 'input' : 'div'])), saved);
global.ws = { readyState: 1, send: (m) => sent.push(JSON.parse(m)) };
load('bots.js');
const el = (id) => p.els[id];
const last = () => sent[sent.length - 1];

const route = (over) => ({ id: 'a1', name: 'Section Z', path: 'n e s', targets: ['angel'],
  step_count: 3, steps_taken: 0, kills: 0, running: false, paused: null, loop: false,
  note: '', ...over });
const ROUTES = [route(), route({ id: 'b2', name: 'Treehouse', path: 'u, {pick fruit;d}',
  targets: ['rat'], step_count: 2 })];

renderBotPanel(ROUTES);
check('nothing chosen: nothing to press', el('bot-name').textContent === 'No bot chosen'
  && el('bot-start').disabled && el('bot-pause').disabled && el('bot-stop').disabled);

const type = (q) => { el('bot-find').value = q; el('bot-find').oninput(); };
const rows = () => el('bot-found').children.filter((c) => c.className === 'bf');
type('rat');
check('search finds it by the creature it hunts',
  rows().length === 1 && rows()[0].children[0].textContent === 'Treehouse');
type('fruit');
check('or by a step in its path', rows().length === 1);
type('zz');
check('says so when nothing matches', el('bot-found').children[0].textContent.includes('No bot'));

type('tree');
rows()[0].children[0].onclick();
check('clicking the name picks it without starting it',
  el('bot-name').textContent === 'Treehouse' && sent.length === 0 && !el('bot-start').disabled
  && saved['bot:route'] === 'b2');
el('bot-start').onclick();
check('Start starts it', same(last(), { t: 'routes', op: 'start', id: 'b2' }));
check('picked but not walking: Clear, not Stop',
  el('bot-stop').textContent === 'Clear' && !el('bot-stop').disabled);

type('sec');
rows()[0].children[2].onclick();
check("a result's own Start starts that one", same(last(), { t: 'routes', op: 'start', id: 'a1' }));

renderBotPanel([route({ running: true, steps_taken: 1 }), ROUTES[1]]);
check('walking: shown, with its step', el('bot-name').textContent === 'Section Z'
  && el('bot-step').textContent === '1 / 3' && el('bot-now').className === 'live');
check('walking: Pause and Stop, not Start',
  el('bot-start').disabled && !el('bot-pause').disabled && !el('bot-stop').disabled
  && el('bot-stop').textContent === 'Stop');
type('tree');
const button = rows()[0].children[2];
check('nothing else starts while one walks', button.disabled);
renderBotPanel([route({ running: true, steps_taken: 2 }), ROUTES[1]]);
check('a step taken does not rebuild the results under the cursor', rows()[0].children[2] === button);

el('bot-pause').onclick();
check('Pause pauses it', same(last(), { t: 'routes', op: 'pause', id: 'a1' }));
renderBotPanel([route({ steps_taken: 2, kills: 1, note: 'paused at step 2 of 3',
  paused: { step: 2, room: 7, room_name: 'A Dark Square', when: '13:20' } }), ROUTES[1]]);
check('paused: says where', el('bot-note').textContent.startsWith('paused in A Dark Square')
  && el('bot-note').textContent.includes('1 killed') && el('bot-now').className === 'held');
check('paused: Resume, and Start is Start over',
  el('bot-pause').textContent === 'Resume' && el('bot-start').textContent === 'Start over');
el('bot-pause').onclick();
check('Resume resumes it', same(last(), { t: 'routes', op: 'resume', id: 'a1' }));
const beforeStop = sent.length;
el('bot-stop').onclick();
check('Stop stops it', same(last(), { t: 'routes', op: 'stop', id: 'a1' }) && sent.length === beforeStop + 1);
check('and takes it off the panel', el('bot-name').textContent === 'No bot chosen'
  && saved['bot:route'] === '' && el('bot-stop').disabled && el('bot-start').disabled,
  el('bot-name').textContent);
renderBotPanel([route({ steps_taken: 2, note: 'stopped' }), ROUTES[1]]);
check('and the server saying it stopped does not bring it back', el('bot-name').textContent === 'No bot chosen');

// A route that ended on its own stays until cleared, so its note can be read.
type('sec');
rows()[0].children[0].onclick();
renderBotPanel([route({ steps_taken: 3, kills: 4, note: 'finished' }), ROUTES[1]]);
check('a finished route stays, with Clear', el('bot-name').textContent === 'Section Z'
  && el('bot-note').textContent === 'finished' && el('bot-stop').textContent === 'Clear');
sent.length = 0;
el('bot-stop').onclick();
check('Clear empties the panel and tells the server nothing',
  el('bot-name').textContent === 'No bot chosen' && sent.length === 0 && saved['bot:route'] === '');
renderBotPanel([route({ paused: { step: 1, room: 7, room_name: 'A Dark Square' } }), ROUTES[1]]);
check('a paused route still shows itself, with Stop', el('bot-name').textContent === 'Section Z'
  && el('bot-stop').textContent === 'Stop');
renderBotPanel(ROUTES);

sent.length = 0;
type('tree');
el('bot-find').onkeydown({ key: 'Enter', preventDefault() {} });
check('Enter picks the first match and starts nothing',
  el('bot-name').textContent === 'Treehouse' && saved['bot:route'] === 'b2',
  el('bot-name').textContent);
check('...and sent nothing', sent.length === 0);

// A /go or a click on the map, shown with Stop and nothing else.
sent.length = 0;
renderBotPanel(ROUTES, { running: true, goal: 'Center of Town', steps: 23, note: '' });
check('a walk shows where it is going', el('bot-name').textContent === 'Walking to Center of Town'
  && el('bot-step').textContent === '23 steps', el('bot-name').textContent);
check('a walk: Stop, and no Start or Pause',
  el('bot-start').disabled && el('bot-pause').disabled && !el('bot-stop').disabled);
el('bot-stop').onclick();
check('Stop stops the walk', same(last(), { t: 'routes', op: 'stop_walk' }), last());
type('tree');
check('nothing else starts during a walk', rows()[0].children[2].disabled);
renderBotPanel(ROUTES, { running: false, goal: 'Center of Town', steps: 23, note: 'finished' });
check('a finished walk leaves the panel', el('bot-name').textContent !== 'Walking to Center of Town'
  && el('bot-stop').textContent !== 'Stop', el('bot-stop').textContent);

finish();
