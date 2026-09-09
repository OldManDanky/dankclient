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
  // an incoming tell is indistinguishable from one you sent.  Arrow both:
  //   ←Someone    they told you
  //   →Someone    you told them
  function speaker(m) {
    return (m.mine ? '→' : '←') + m.who;
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
    if (all.length < 2) return;         // nothing to choose between
    for (const tag of all) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = tag;
      if (!muted.has(tag)) b.className = 'on';
      b.title = muted.has(tag) ? `show ${tag}` : `hide ${tag}`;
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
  }

  // --- the list -------------------------------------------------------------

  function render() {
    const atBottom =
      bodyEl.scrollHeight - bodyEl.scrollTop - bodyEl.clientHeight < 24;
    bodyEl.replaceChildren();

    const shown = messages.filter((m) => !muted.has(m.channel || 'other'));
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
        (m.mine ? ' mine' : '');
      row.title = new Date((m.at || 0) * 1000).toLocaleTimeString() +
        '  |  ' + (m.channel || '') + '  |  ' + (m.text || '');

      const txt = document.createElement('span');
      txt.className = 'cm-txt';
      txt.textContent = m.text || '';

      row.onclick = () => {
        const prefix = replyFor(m);
        if (!prefix) return;
        const cmd = document.getElementById('cmd');
        cmd.value = prefix;
        cmd.focus();
      };

      // BAB is the other way round from CAA: its message often omits the name
      // ("moos at you."), so a tell still needs a speaker beside it.
      if (m.kind === 'tell') {
        const who = document.createElement('span');
        who.className = 'cm-who';
        who.textContent = speaker(m);
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
          text: d.message, mine: !!d.from_me }
      : { kind, at: Date.now() / 1000, who: d.who, channel: d.channel,
          command: d.command, text: d.message, mine: false });
    if (messages.length > LIMIT * 2) messages = messages.slice(-LIMIT);
    refresh();
  };

  refresh();
})();
