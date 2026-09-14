// Options -> Layout -> Vitals: which of them show, and where the strip sits.
'use strict';

const { page, load, check, finish } = require('./stage');

const saved = {};
let p;
function open(renamed) {
  p = page({ msgmon: 'div', mapmon: 'div', botpanel: 'div', roompanel: 'div',
    'panel-toggles': 'div', vitals: 'div', 'v-hp': 'div', 'v-sp': 'div', 'v-gp1': 'div',
    'v-gp2': 'div', guild: 'div', 'lbl-hp': 'b', 'lbl-sp': 'b', 'lbl-gp1': 'b', 'lbl-gp2': 'b',
    'vital-toggles': 'div' }, saved);
  p.els['lbl-gp1'].textContent = renamed || 'GP1';
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

finish();
