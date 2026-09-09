/* The map.

   Rooms have no coordinates -- 3K never sends any -- so the layout is made
   here, by walking outward from where you stand and stepping one cell per
   compass move.  That is a drawing, not a claim about geography: MUD areas
   are routinely non-Euclidean, and two rooms can genuinely want the same
   square.  When they collide the newcomer is nudged to a free cell and its
   link is drawn as a line, so the picture stays readable and no room is
   hidden underneath another.

   Exits that are not compass directions -- "enter", "vortex", "climb pipe" --
   get no direction to step in, so they are drawn dashed to the nearest free
   cell.  They are usually where one area ends and the next begins. */

(function () {
  const root = document.getElementById('mapmon');
  if (!root) return;

  const canvas = root.querySelector('canvas');
  const label = root.querySelector('.map-where');
  const ctx = canvas.getContext('2d');

  const STEP = {
    n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0],
    ne: [1, -1], nw: [-1, -1], se: [1, 1], sw: [-1, 1],
  };
  const CELL = 30;
  const DOT = 13;

  let state = null;          // last {centre, rooms} from the server
  let placed = new Map();    // room id -> {x, y}
  let hits = [];             // {x, y, id} in canvas pixels, for clicking

  // The view does not move and does not scale.  Where you are is the middle,
  // always, at one size -- a map you can drag off centre or zoom out of is a
  // map that needs putting back before it can be read, and the whole point of
  // it is being readable at a glance without being touched.

  // Docked at the top of the sidebar rather than floating over the terminal,
  // so there is no position or size to remember -- only whether it is rolled
  // up.  The header is the whole control: click it to collapse.
  const store = window.prefs;
  const COLLAPSED = 'cm:mapmon:collapsed';
  const collapsed = () => root.classList.contains('collapsed');

  function setCollapsed(on) {
    root.classList.toggle('collapsed', on);
    const toggle = root.querySelector('.cm-toggle');
    if (toggle) toggle.textContent = on ? '+' : '\u2212';
    if (store) store.set(COLLAPSED, on ? '1' : '');
    if (!on) draw();
  }

  setCollapsed(store ? store.get(COLLAPSED, '') === '1' : false);
  root.querySelector('header').onclick = () => setCollapsed(!collapsed());

  // The box changes with the window, and goes from nothing to something when
  // the panel is switched back on -- a canvas sized from a display:none box
  // is a canvas one pixel wide.
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => {
      try {
        draw();
      } catch (err) {
        console.error('map resize', err);
      }
    }).observe(root.querySelector('.map-body'));
  }

  // A stable hue per area, so the same place is the same colour every time
  // you look and neighbouring areas read apart at a glance.  Regions are a
  // label over a flat graph, so this is the only place they exist at all.
  function areaHue(region) {
    let h = 0;
    for (const ch of String(region)) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return h;
  }

  function css(name, fallback) {
    const v = getComputedStyle(document.body).getPropertyValue(name).trim();
    return v || fallback;
  }

  // --- layout ---------------------------------------------------------------

  /* Lay out only what will be seen.

     The server sends a couple of hundred rooms; a panel this size holds
     perhaps sixty.  Placing them all filled the map with long lines running
     to rooms flung wherever a cell happened to be free -- which said nothing
     true about the geography and buried the part that did.

     So: rooms outside the visible grid are not placed at all, and a room
     whose square is taken moves at most one ring before being dropped. */
  function layout(map, halfX, halfY) {
    placed = new Map();
    if (!map || map.centre == null) return;
    if (typeof map.rooms !== 'object' || !map.rooms[map.centre]) return;

    const taken = new Set(['0,0']);
    placed.set(map.centre, { x: 0, y: 0, moved: false, from: [0, -1] });

    const claim = (id, x, y, came) => {
      if (Math.abs(x) > halfX || Math.abs(y) > halfY) return false;
      for (let r = 0; r <= 1; r++) {
        for (let dx = -r; dx <= r; dx++) {
          for (let dy = -r; dy <= r; dy++) {
            if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
            const key = `${x + dx},${y + dy}`;
            if (!taken.has(key)) {
              taken.add(key);
              placed.set(id, { x: x + dx, y: y + dy, moved: r > 0, from: came });
              return true;
            }
          }
        }
      }
      return false;                     // no room for it; leave it off
    };

    // Where to put a room reached by something that is not a direction --
    // "onward", "doorway", "enter".  The Tree of Life is a straight run of
    // them and nothing else, so a rule that gives up on them leaves twenty
    // rooms piled on one square with their links drawn across the map.
    // Carrying on the way we were already going draws the line the area
    // actually is; failing that, any free side will do.
    const AROUND = [[1, 0], [0, 1], [-1, 0], [0, -1],
                    [1, 1], [-1, 1], [1, -1], [-1, -1]];

    function drift(from) {
      const [fx, fy] = from.from || [1, 0];
      for (const [dx, dy] of [[fx, fy], ...AROUND]) {
        if (!taken.has(`${from.x + dx},${from.y + dy}`)) return [dx, dy];
      }
      return [fx, fy];
    }

    // Breadth-first, so the squares nearest you are claimed first and the
    // ones that get dropped are the ones furthest away.  Compass exits are
    // taken first at every room, so real geometry always wins the square.
    const queue = [map.centre];
    while (queue.length) {
      const id = queue.shift();
      const from = placed.get(id);
      const room = map.rooms[id];
      if (!from || !room) continue;
      const links = Object.entries(room.exits);
      for (const pass of [0, 1]) {
        for (const [command, to] of links) {
          const step = STEP[command];
          if ((pass === 0) !== Boolean(step)) continue;
          if (placed.has(to) || !map.rooms[to]) continue;
          const [dx, dy] = step || drift(from);
          if (claim(to, from.x + dx, from.y + dy, [dx, dy])) queue.push(to);
        }
      }
    }
  }

  // --- drawing --------------------------------------------------------------

  function draw() {
    // A blank panel says nothing about why it is blank.  Anything that goes
    // wrong in here gets painted where the map should have been.
    try {
      paint();
    } catch (err) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = '#c8553d';
      ctx.font = '11px Consolas, monospace';
      ctx.fillText('map: ' + (err && err.message ? err.message : err), 8, 16);
      console.error('map', err);
    }
  }

  function paint() {
    if (collapsed()) return;
    let box = canvas.parentElement.getBoundingClientRect();
    if (box.width < 8 || box.height < 8) {
      // Measured before the panel has been laid out, or squeezed flat by a
      // flex rule.  Fall back to the frame minus the rows above and below,
      // so the first draw after a reload still puts something on screen.
      const frame = root.getBoundingClientRect();
      const chrome = (root.querySelector('header').offsetHeight || 24) +
                     (label.offsetHeight || 20);
      box = { width: Math.max(40, frame.width),
              height: Math.max(40, frame.height - chrome) };
    }
    const dpr = devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    canvas.style.width = box.width + 'px';
    canvas.style.height = box.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    hits = [];

    ctx.font = '11px Consolas, monospace';
    if (state && typeof state.rooms !== 'object') {
      // An older server sends `rooms` as a count and no `centre` at all.
      // Object.entries(4) is [], so this drew a blank panel and called it an
      // empty map -- say what it really is instead.
      ctx.fillStyle = '#c8553d';
      ctx.fillText('server is older than this page - restart the client', 8, 18);
      return;
    }
    if (!state || state.centre == null) {
      ctx.fillStyle = css('--dim', '#7c8598');
      ctx.fillText(state && state.lost ? 'lost - walk a room or two'
                                       : 'nothing mapped yet', 10, 20);
      return;
    }

    const cell = CELL;
    const dot = DOT;
    // Re-lay out for the space actually available, so what is drawn is what
    // fits.  Cheap: a few hundred rooms and no DOM.
    //
    // Half a cell short of the edge, so a room that is placed is a room whose
    // square is wholly on screen.  Rounding outward instead put rooms past
    // both edges: they were culled from the picture but not from the grid, so
    // they took squares from rooms that would have been visible and left
    // their links running off the sides -- which reads as a map that has
    // slipped rather than one that ends.
    layout(state, Math.floor((box.width / 2 - dot) / cell),
           Math.floor((box.height / 2 - dot) / cell));
    const cx = box.width / 2;
    const cy = box.height / 2;
    const at = (p) => [cx + p.x * cell, cy + p.y * cell];

    // Within the canvas, dot and all.
    const onScreen = (p) => {
      const [x, y] = at(p);
      return x >= dot / 2 && y >= dot / 2
          && x <= box.width - dot / 2 && y <= box.height - dot / 2;
    };

    const line = css('--line', '#2a2f3a');
    const ink = css('--ink', '#d8dde6');
    const dim = css('--dim', '#7c8598');
    const accent = css('--accent', '#6f9beb');

    // links first, so rooms sit on top of them
    for (const [id, room] of Object.entries(state.rooms)) {
      const a = placed.get(Number(id));
      if (!a || !onScreen(a)) continue;
      const [ax, ay] = at(a);
      for (const [command, to] of Object.entries(room.exits)) {
        const b = placed.get(to);
        if (!b || !onScreen(b)) continue;   // the other end is not drawn
        const [bx, by] = at(b);
        const near = Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y)) <= 1;
        const straight = STEP[command] !== undefined && !b.moved && !a.moved;
        ctx.beginPath();
        ctx.setLineDash(straight ? [] : [2, 3]);
        ctx.strokeStyle = straight ? line : dim;
        ctx.lineWidth = 1;
        if (near) {
          ctx.moveTo(ax, ay);
          ctx.lineTo(bx, by);
        } else {
          // Not next door, so a line between them would run across the map
          // without saying anything true.  Every room in the Tree of Life has
          // a "turnaway" back to its entrance, and drawing twenty-one of
          // those buried the line the area actually is.  A stub pointing the
          // right way says as much and takes no space.
          const len = Math.hypot(bx - ax, by - ay) || 1;
          const ux = (bx - ax) / len;
          const uy = (by - ay) / len;
          ctx.moveTo(ax + ux * dot * 0.7, ay + uy * dot * 0.7);
          ctx.lineTo(ax + ux * cell * 0.45, ay + uy * cell * 0.45);
        }
        ctx.stroke();
      }
    }
    ctx.setLineDash([]);

    // Stubs for exits nobody has walked: DDD lists every way out of a room,
    // an edge only exists once you have taken one, and the difference is
    // where there is still something to find.
    for (const [rawId, room] of Object.entries(state.rooms)) {
      const p = placed.get(Number(rawId));
      if (!p || !onScreen(p)) continue;
      const [ax, ay] = at(p);
      // A way out of the area is drawn the same as one nobody has walked:
      // the room it leads to is not drawn here, so all there is to say is
      // that it leaves.  Which is also what the edge of the panel needs: a
      // link to a room just past it used to be a line running off the side,
      // and a stub says the same without pretending to reach anything.
      const away = Object.entries(room.exits)
        .filter(([, to]) => {
          const q = placed.get(to);
          return !q || !onScreen(q);
        })
        .map(([command]) => command);
      for (const command of [...(room.unwalked || []), ...away]) {
        const step = STEP[command];
        ctx.strokeStyle = dim;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        if (step) {
          ctx.moveTo(ax + step[0] * dot * 0.6, ay + step[1] * dot * 0.6);
          ctx.lineTo(ax + step[0] * cell * 0.42, ay + step[1] * cell * 0.42);
        } else {
          // No direction to point in, so mark the room itself as having one.
          ctx.arc(ax + dot * 0.75, ay - dot * 0.75, 1.8, 0, Math.PI * 2);
        }
        ctx.stroke();
      }
    }
    ctx.setLineDash([]);

    for (const [rawId, room] of Object.entries(state.rooms)) {
      const id = Number(rawId);
      const p = placed.get(id);
      if (!p) continue;
      if (!onScreen(p)) continue;
      const [x, y] = at(p);
      const here = id === state.centre;
      const tint = room.region == null
        ? null : `hsl(${areaHue(room.region)} 42% 34%)`;
      ctx.fillStyle = here ? accent : (tint || (room.name ? '#333a48' : '#262b36'));
      ctx.strokeStyle = here ? accent : line;
      ctx.beginPath();
      ctx.roundRect(x - dot / 2, y - dot / 2, dot, dot, 2);
      ctx.fill();
      ctx.stroke();
      // You are always in the middle of the panel, but a square in the
      // middle of a dozen identical squares is not obviously the middle.
      // A ring says which one.
      if (here) {
        ctx.strokeStyle = accent;
        ctx.globalAlpha = 0.45;
        ctx.beginPath();
        ctx.arc(x, y, dot, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      hits.push({ x, y, r: dot, id, name: room.name, exits: room.exits,
                 unwalked: room.unwalked, area: room.area });
    }


    const room = state.rooms[state.centre];
    label.textContent = (state.name || 'unnamed room') +
      (room ? `  ·  ${Object.keys(room.exits).length} known exits` : '');
    const area = (state.region || []).join(' \u203a ');
    if (area) label.textContent = area + '  \u00b7  ' + label.textContent;
    label.title = area;
  }

  // --- interaction ----------------------------------------------------------

  function pick(e) {
    const box = canvas.getBoundingClientRect();
    const px = e.clientX - box.left;
    const py = e.clientY - box.top;
    return hits.find((h) => Math.abs(h.x - px) <= h.r && Math.abs(h.y - py) <= h.r);
  }

  canvas.addEventListener('mousemove', (e) => {
    const hit = pick(e);
    canvas.style.cursor = hit ? 'pointer' : 'default';
    canvas.title = hit
      ? [`#${hit.id}  ${hit.name || 'unnamed'}`,
         hit.area ? hit.area.join(' \u203a ') : 'no area',
         'walked: ' + (Object.keys(hit.exits).join(' ') || 'none'),
         'unwalked: ' + ((hit.unwalked || []).join(' ') || 'none'),
         'click to walk here \u00b7 double-click to rename'].join('\n')
      : '';
  });

  // Dead reckoning is inference and inference is sometimes wrong, so any
  // room can be renamed by hand -- including the ones the MUD never named.
  canvas.addEventListener('dblclick', (e) => {
    const hit = pick(e);
    if (!hit) return;
    const name = prompt(`Name for room #${hit.id}`, hit.name || '');
    if (name === null) return;
    if (window.ws) {
      window.ws.send(JSON.stringify({ t: 'rename', room: hit.id, name }));
    }
  });

  canvas.addEventListener('click', (e) => {
    const hit = pick(e);
    if (!hit || hit.id === state.centre) return;
    if (window.ws) window.ws.send(JSON.stringify({ t: 'walk', to: hit.id }));
  });

  window.renderMap = function (map) {
    // Called with nothing at all: draw what is already here.  The panel being
    // switched back on is not news about the map.
    if (map === undefined) {
      draw();
      return;
    }
    // The server sends the rooms only when the view has actually changed;
    // otherwise it says so and we keep the ones we have.
    if (map && map.unchanged && state) {
      Object.assign(state, map, { rooms: state.rooms, centre: state.centre });
      draw();
      return;
    }
    state = map;
    draw();
  };
  addEventListener('resize', draw);
})();
