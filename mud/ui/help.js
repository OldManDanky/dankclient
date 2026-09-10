/* The "/" commands, where somebody might find them.

   They lived only in the terminal, which meant the only way to learn what this
   client does was to already know that /help existed. Grouped by what you are
   trying to do rather than listed, because thirty-five lines in one column is
   a list nobody reads. */

(function () {
  const $ = (id) => document.getElementById(id);
  let drawn = false;

  function ask() {
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'help' }));
    }
  }

  window.handleHelp = function (m) {
    if (!m || !m.groups || drawn) return;
    drawn = true;
    const box = $('help-groups');
    box.replaceChildren();
    for (const group of m.groups) {
      const el = document.createElement('div');
      el.className = 'help-group';
      const title = document.createElement('h5');
      title.textContent = group.title;
      el.append(title);
      if (group.blurb) {
        const why = document.createElement('p');
        why.textContent = group.blurb;
        el.append(why);
      }
      for (const row of group.rows) {
        const line = document.createElement('div');
        line.className = 'help-row';
        const go = document.createElement('button');
        go.type = 'button';
        go.textContent = row.verb;
        // The commands take arguments, so this loads it rather than runs it:
        // "/go " with the cursor after it is the useful thing.
        go.onclick = () => {
          const box2 = document.getElementById('cmd');
          const bare = row.verb.split(' ')[0];
          box2.value = row.verb.includes('<') || row.verb.includes('[')
            ? bare + ' ' : bare;
          if (window.options) window.options.close();
          box2.focus();
        };
        const what = document.createElement('span');
        what.textContent = row.what;
        line.append(go, what);
        el.append(line);
      }
      box.append(el);
    }
  };

  if (window.whenConnected) window.whenConnected(ask);
})();
