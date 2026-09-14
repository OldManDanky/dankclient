// Options -> Layout -> Vitals: which of them show, and where the strip sits.
'use strict';

const { El, page, load, check, finish } = require('./stage');

const saved = {};
let p;
function open(renamed) {
  p = page({ msgmon: 'div', mapmon: 'div', botpanel: 'div', roompanel: 'div',
    'panel-toggles': 'div', vitals: 'div', 'v-hp': 'div', 'v-sp': 'div', 'v-gp1': 'div',
    'v-gp2': 'div', guild: 'div', 'lbl-hp': 'b', 'lbl-sp': 'b', 'lbl-gp1': 'b', 'lbl-gp2': 'b',
    'vital-toggles': 'div' }, saved);
  p.els['lbl-gp1'].textContent = renamed || 'GP1';
  for (const id of ['botpanel', 'roompanel']) {
    const head = new El('h2');
    const sign = new El('span');
    sign.className = 'cm-toggle';
    head.append(sign);
    p.els[id].append(head);
  }
  load('panels.js');
}
const box = (name) => p.els['vital-toggles'].querySelector(`input[name=${name}]`);
const off = (id) => p.els[id].classList.contains('v-off');
const flip = (name, on) => { const b = box(name); b.checked = on; b.onchange(); };

open('Endurance');
check('everything shows until asked otherwise',
  ['vitals', 'v-hp', 'v-sp', 'v-gp1', 'v-gp2', 'guild'].every((id) => !off(id))
  && !document.body.classList.contains('vitals-below'));
check('a gauge you renamed is listed by your name for it',
  box('vital-v-gp1') && box('vital-v-gp1').parent.children[1].textContent === 'Endurance');

flip('vital-v-gp2', false);
check('unticking GP2 hides it, and only it', off('v-gp2') && !off('v-hp') && !off('vitals'));
flip('vital-guild', false);
check('the guild line can go too', off('guild'));
const where = p.els['vital-toggles'].querySelector('select');
where.value = 'below';
where.onchange();
check('the strip can sit under the command box',
  document.body.classList.contains('vitals-below') && saved['vitals:where'] === 'below');
flip('vitals-strip', false);
check('or not be there at all', off('vitals'));

open();
check('a reload keeps all of it',
  off('v-gp2') && off('guild') && off('vitals') && !off('v-hp')
  && document.body.classList.contains('vitals-below')
  && !box('vital-v-gp2').checked && box('vital-v-hp').checked);
flip('vitals-strip', true);
flip('vital-v-gp2', true);
check('and ticking them again brings them back', !off('vitals') && !off('v-gp2'));

// Rolling the sidebar's panels up to their headings, as the map does.
const heading = (id) => p.els[id].querySelector('h2');
const rolled = (id) => p.els[id].classList.contains('collapsed');
check('open until rolled up', !rolled('botpanel') && !rolled('roompanel'));
heading('botpanel').onclick();
check('a click on the Stepper heading rolls it up, and the sign says so',
  rolled('botpanel') && !rolled('roompanel') && heading('botpanel').querySelector('.cm-toggle').textContent === '+'
  && saved['cm:botpanel:collapsed'] === '1');
open();
check('a reload keeps it rolled up', rolled('botpanel'));
heading('botpanel').onclick();
check('and another click opens it again', !rolled('botpanel') && saved['cm:botpanel:collapsed'] === '');

finish();
