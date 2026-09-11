// What the map panel says when it has nothing to draw.
'use strict';

const { El, page, load, check, finish } = require('./stage');

const written = [];
global.__pen = {
  font: '', fillStyle: '', lineWidth: 0, lineCap: '', globalAlpha: 1,
  setTransform() {}, clearRect() {}, fillText: (t) => written.push(t),
  beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
  arc() {}, rect() {}, roundRect() {}, save() {}, restore() {},
  setLineDash() {}, measureText: () => ({ width: 30 }),
  createLinearGradient: () => ({ addColorStop() {} }),
};

const p = page({ mapmon: 'div' });
const root = p.els.mapmon;
const canvas = new El('canvas');
const where = new El('div');
where.className = 'map-where';
root.append(new El('header'), canvas, where);
canvas.parentElement = root;
root.rect = { top: 0, width: 220, height: 160 };
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.devicePixelRatio = 1;

load('map.js');

const said = (map) => { written.length = 0; renderMap(map); return written.join(' | '); };

// A fresh install whose first-run fetch did not land: the map is empty, and
// it is locked, so no amount of walking will put a room in it.
check('an empty map says to go and fetch one',
      said({ centre: null, lost: true, known_rooms: 0, rooms: {} })
        === 'no map yet - Options > Updates',
      said({ centre: null, lost: true, known_rooms: 0, rooms: {} }));

// 3kdb's map, and it simply does not recognise this room.
check('lost on a map that has rooms is still lost',
      said({ centre: null, lost: true, known_rooms: 49494, rooms: {} })
        === 'lost - walk a room or two',
      said({ centre: null, lost: true, known_rooms: 49494, rooms: {} }));

check('and before anything has arrived at all',
      said({ centre: null, lost: false, known_rooms: 49494, rooms: {} })
        === 'nothing mapped yet',
      said({ centre: null, lost: false, known_rooms: 49494, rooms: {} }));

finish();
