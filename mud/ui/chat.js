/* Messages: tells, emotes and channel traffic, in one window.

   MIP separates the two -- BAB is personal traffic, CAA is channels -- and
   Portal drew the same line, so this was two panels for a while.  Two panels
   that could be dragged anywhere meant two things to place and two things
   sitting over the output; and the split was the MUD's idea of the difference
   rather than the reader's.  One window, with a tag per channel and `tell` as
   one more of them, says the same and asks nothing.

   The MUD prints all of it in the main output too, which is what makes this a
   second view rather than a third copy: it keeps a conversation readable while
   combat scrolls past. */

(function () {
  const LIMIT = 300;
  const ID = 'msgmon';
  const store = window.prefs;

  const root = document.getElementById(ID);
  if (!root) return;

  const bodyEl = root.querySelector('.cm-body');
  const filterEl = root.querySelector('.cm-filters');
  const countEl = root.querySelector('.cm-count');
  const toggleEl = root.querySelector('.cm-toggle');

  let messages = [];
  let seeded = false;

  let muted = new Set();
  try {
    muted = new Set(JSON.parse(store.get(`cm:${ID}:muted`, '[]')));
  } catch (err) { /* a bad preference is no preference */ }

  /* Colours, chosen by right-clicking a line.

     They stick to a channel or to a person rather than to the one line: a
     single coloured line scrolls away, and what somebody wants is every clan
     line green, or everything one friend says in gold.  A person's colour
     wins over their channel's, being the more particular choice.  Light
     enough to read on the window's dark ground, all of them. */
  const PALETTE = [
    ['red', '#ff7b72'], ['orange', '#ffa657'], ['yellow', '#f2cc60'],
    ['green', '#7ee787'], ['teal', '#56d4dd'], ['blue', '#79c0ff'],
    ['violet', '#d2a8ff'], ['pink', '#ff9bce'],
  ];
  let colours = { channel: {}, who: {} };
  try {
    const got = JSON.parse(store.get(`cm:${ID}:colours`, '{}'));
    colours = { channel: got.channel || {}, who: got.who || {} };
  } catch (err) { /* a bad preference is no preference */ }

  function saveColours() {
    store.set(`cm:${ID}:colours`, JSON.stringify(colours));
  }

  // People by name whatever the case the MUD used; channels exactly as named.
  const personKey = (who) => String(who || '').trim().toLowerCase();

  function colourOf(m) {
    return (m.who && colours.who[personKey(m.who)])
      || colours.channel[m.channel || 'other'] || '';
  }

  /* Your own lines, hidden on request: "I want to see what everybody else
     says, not what I sent."  A tell says itself which way it went; a channel
     line is yours when its speaker is your character, which the server tells
     us however you logged in. */
  let me = '';
  let hideMine = store.get(`cm:${ID}:hidemine`, '') === '1';

  function isMine(m) {
    return !!m.mine || (!!me && !!m.who && personKey(m.who) === me);
  }

  /* Dings, chosen from the same right-click menu as the colours: every line
     on a channel, or anything from a person.  Never for your own lines, and
     never for a channel you have hidden -- hiding it says you are not
     listening.  The sound itself is sound.js's. */
  let dings = { channel: {}, who: {} };
  try {
    const got = JSON.parse(store.get(`cm:${ID}:dings`, '{}'));
    dings = { channel: got.channel || {}, who: got.who || {} };
  } catch (err) { /* a bad preference is no preference */ }

  function saveDings() {
    store.set(`cm:${ID}:dings`, JSON.stringify(dings));
  }

  function wantsDing(m) {
    if (isMine(m) || muted.has(m.channel || 'other')) return false;
    return !!((m.who && dings.who[personKey(m.who)])
      || dings.channel[m.channel || 'other']);
  }

  window.setMe = function (name) {
    const key = personKey(name);
    if (key === me) return;
    me = key;
    refresh();
  };

  // --- the frame ------------------------------------------------------------

  function collapsed() {
    return root.classList.contains('collapsed');
  }

  function setCollapsed(on) {
    root.classList.toggle('collapsed', on);
    if (toggleEl) toggleEl.textContent = on ? '+' : '−';
    store.set(`cm:${ID}:collapsed`, on ? '1' : '');
    if (!on) bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  setCollapsed(store.get(`cm:${ID}:collapsed`, '') === '1');
  root.querySelector('header').onclick = () => setCollapsed(!collapsed());

  // --- reading a line -------------------------------------------------------

  // BAB names the other party either way, so the direction has to be shown or
  // an incoming tell is indistinguishable from one you sent.  In words, the
  // way the MUD says it, rather than arrows somebody has to learn:
  //   Someone tells you:   they told you
  //   You tell Someone:    you told them
  // A soul -- an emote sent over tell -- is not something said, so it is not
  // "tells you:".  The server works out which it was from what 3K printed.
  function speaker(m) {
    return m.mine ? `You tell ${m.who}:` : `${m.who} tells you:`;
  }

  // CAA's last field is the line the MUD already printed, and every channel
  // formats itself differently:
  //
  //   [Clan] Someone : moo         a tag in front
  //   Someone shouts: BIG MOO      the verb carries the channel
  //   Speaker <HM-Oracle>: ...    the speaker wears a title
  //   [PARTY] All gold divvied     nobody speaking at all
  //
  // Each already says who and where, so a chat row prints the line verbatim
  // with nothing beside it.  Columns of our own repeated it -- "Shout  Someone
  // shouts: BIG MOO" -- and had no right answer for the party lines, which
  // have no speaker to strip.

  // The channel's display name is for reading ("Clan Sa", "High Mortal"); its
  // command is what you type back ("ctell", "hm").
  function replyFor(m) {
    if (m.kind === 'tell') return m.who ? `tell ${m.who} ` : '';
    return m.command ? `${m.command} ` : '';
  }

  // --- tags -----------------------------------------------------------------

  /* Every channel that has said anything, plus `tell` when there are any.

     Built from the traffic rather than from a list, because the list is the
     character's: guild and clan channels differ per character, and one that
     nobody has spoken on is a tag with nothing behind it. */
  function tags() {
    return [...new Set(messages.map((m) => m.channel || 'other'))].sort();
  }

  function renderTags() {
    const all = tags();
    filterEl.replaceChildren();
    const anyMine = hideMine || messages.some(isMine);
    if (all.length < 2 && !anyMine) return;         // nothing to choose between
    for (const tag of all.length >= 2 ? all : []) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = tag;
      if (!muted.has(tag)) b.className = 'on';
      if (dings.channel[tag]) b.className = `${b.className} dings`.trim();
      b.title = (muted.has(tag) ? `show ${tag}` : `hide ${tag}`)
        + (dings.channel[tag] ? ' (dings)' : '');
      // The channel's colour under its tag, so the key is on screen.
      if (colours.channel[tag]) {
        b.style.boxShadow = `inset 0 -2px 0 ${colours.channel[tag]}`;
      }
      b.onclick = (e) => {
        // The header collapses on a click and the tags sit under it.
        e.stopPropagation();
        if (muted.has(tag)) muted.delete(tag);
        else muted.add(tag);
        store.set(`cm:${ID}:muted`, JSON.stringify([...muted]));
        renderTags();
        render();
      };
      filterEl.append(b);
    }
    if (anyMine) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = 'mine';
      b.className = 'mine' + (hideMine ? '' : ' on');
      b.title = hideMine ? 'show what you said' : 'hide what you said';
      b.onclick = (e) => {
        e.stopPropagation();
        hideMine = !hideMine;
        store.set(`cm:${ID}:hidemine`, hideMine ? '1' : '');
        refresh();
      };
      filterEl.append(b);
    }
  }

  // --- the list -------------------------------------------------------------

  function render() {
    const atBottom =
      bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight < 24;
    bodyEl.replaceChildren();

    const shown = messages.filter((m) => !muted.has(m.channel || 'other')
      && !(hideMine && isMine(m)));
    const hidden = messages.length - shown.length;
    countEl.textContent = shown.length
      ? String(shown.length) + (hidden ? ` of ${messages.length}` : '')
      : '';

    if (!shown.length) {
      const empty = document.createElement('div');
      empty.className = 'cm-empty';
      empty.textContent = messages.length
        ? 'everything is filtered out' : 'nothing said yet';
      bodyEl.append(empty);
      return;
    }

    for (const m of shown.slice(-LIMIT)) {
      const row = document.createElement('div');
      row.className = 'cm-msg' + (m.kind === 'tell' ? ' tell' : '') +
        (m.soul ? ' soul' : '') + (m.mine ? ' mine' : '');
      row.title = new Date((m.at || 0) * 1000).toLocaleTimeString() +
        '  |  ' + (m.channel || '') + '  |  ' + (m.text || '') +
        '\nright-click to colour';

      const txt = document.createElement('span');
      txt.className = 'cm-txt';
      txt.textContent = m.text || '';
      const colour = colourOf(m);
      if (colour) txt.style.color = colour;

      row.oncontextmenu = (e) => {
        e.preventDefault();
        e.stopPropagation();
        openMenu(e.clientX, e.clientY, m);
      };

      row.onclick = () => {
        const prefix = replyFor(m);
        if (!prefix) return;
        const cmd = document.getElementById('cmd');
        cmd.value = prefix;
        cmd.focus();
      };

      // BAB is the other way round from CAA: its message often omits the name
      // ("moos at you."), so a tell still needs a speaker beside it.
      if (m.kind === 'tell' && m.soul && !m.mine) {
        // As 3K prints it, less "From afar,": "Someone moos at you."
        txt.textContent = `${m.who} ${m.text || ''}`;
        row.append(txt);
      } else if (m.kind === 'tell') {
        const who = document.createElement('span');
        who.className = 'cm-who';
        who.textContent = m.soul ? `To ${m.who}:` : speaker(m);
        if (colour) who.style.color = colour;
        if (m.soul && m.text) {
          // "you moo at Someone." -- and half of them never name who it went to.
          txt.textContent = m.text.charAt(0).toUpperCase() + m.text.slice(1);
        }
        row.append(who, txt);
      } else {
        row.append(txt);
      }
      bodyEl.append(row);
    }
    if (atBottom) bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  function refresh() {
    renderTags();
    render();
  }

  // --- the colour menu -------------------------------------------------------

  let menu = null;

  function closeMenu() {
    if (!menu) return;
    menu.remove();
    menu = null;
    document.removeEventListener('mousedown', outside, true);
    document.removeEventListener('keydown', onKey, true);
  }

  function outside(e) {
    if (menu && !menu.contains(e.target)) closeMenu();
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();          // Escape closes this, not the panels too
      closeMenu();
    }
  }

  /* One row of swatches, for a channel or for a person.  Picking the colour
     already chosen takes it off again, as does "none". */
  function swatches(title, table, key) {
    const part = document.createElement('div');
    const head = document.createElement('h6');
    head.textContent = title;
    const row = document.createElement('div');
    row.className = 'cm-swatches';
    const pick = (value) => {
      if (value && table[key] !== value) table[key] = value;
      else delete table[key];
      saveColours();
      closeMenu();
      refresh();
    };
    for (const [name, value] of PALETTE) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'cm-swatch' + (table[key] === value ? ' on' : '');
      b.style.background = value;
      b.title = name;
      b.setAttribute('aria-label', name);
      b.onclick = () => pick(value);
      row.append(b);
    }
    const none = document.createElement('button');
    none.type = 'button';
    none.className = 'cm-swatch none';
    none.textContent = 'none';
    none.onclick = () => pick('');
    row.append(none);
    part.append(head, row);
    return part;
  }

  /* The Ding row: every line on this channel, anything from this person.
     Turning one on plays it once, so you know what you will be listening for. */
  function dingRow(m, channel) {
    const part = document.createElement('div');
    const head = document.createElement('h6');
    head.textContent = 'Ding';
    const row = document.createElement('div');
    row.className = 'cm-dings';
    const toggle = (label, table, key) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'cm-ding' + (table[key] ? ' on' : '');
      b.textContent = label;
      b.setAttribute('aria-pressed', table[key] ? 'true' : 'false');
      b.onclick = () => {
        if (table[key]) delete table[key];
        else table[key] = true;
        saveDings();
        closeMenu();
        refresh();
        if (table[key] && window.ding) window.ding(channel === 'tell' ? 'tell' : 'channel', true);
      };
      row.append(b);
    };
    toggle(channel === 'tell' ? 'every tell' : `every ${channel} line`,
           dings.channel, channel);
    if (m.who) toggle(`anything from ${m.who}`, dings.who, personKey(m.who));
    part.append(head, row);
    return part;
  }

  function openMenu(x, y, m) {
    closeMenu();
    menu = document.createElement('div');
    menu.className = 'cm-menu';
    menu.setAttribute('role', 'menu');
    const channel = m.channel || 'other';
    menu.append(swatches(channel === 'tell' ? 'All tells' : `The ${channel} channel`,
                         colours.channel, channel));
    if (m.who) {
      menu.append(swatches(`Everything from ${m.who}`,
                           colours.who, personKey(m.who)));
    }
    menu.append(dingRow(m, channel));
    document.body.append(menu);
    // Beside the pointer, but never off the edge of the window.
    const box = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(x, innerWidth - box.width - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(y, innerHeight - box.height - 4))}px`;
    document.addEventListener('mousedown', outside, true);
    document.addEventListener('keydown', onKey, true);
    const first = menu.querySelector('button');
    if (first) first.focus();
  }

  addEventListener('resize', closeMenu);
  bodyEl.addEventListener('scroll', closeMenu);

  // --- from the server ------------------------------------------------------

  window.seedMessages = function (list) {
    if (seeded) return;                 // history only on the first snapshot
    seeded = true;
    messages = list.slice();
    refresh();
  };

  window.pushMessage = function (kind, d) {
    messages.push(kind === 'tell'
      ? { kind, at: Date.now() / 1000, who: d.who, channel: 'tell',
          text: d.message, mine: !!d.from_me, soul: !!d.soul }
      : { kind, at: Date.now() / 1000, who: d.who, channel: d.channel,
          command: d.command, text: d.message, mine: false });
    const latest = messages[messages.length - 1];
    if (wantsDing(latest) && window.ding) {
      window.ding(latest.kind === 'tell' ? 'tell' : 'channel');
    }
    if (messages.length > LIMIT * 2) messages = messages.slice(-LIMIT);
    refresh();
  };

  refresh();
})();
