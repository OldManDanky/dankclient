/* What this client is, and where it keeps things.

   Installed, it says none of this: it lands somewhere without announcing it,
   and afterwards there is a Start Menu entry and no way to find out what it
   did. "Where is my map" gets asked more than once -- before an update,
   before a backup, when something has gone wrong -- and a client that cannot
   answer it is one you have to go looking through a filesystem for. */

(function () {
  const $ = (id) => document.getElementById(id);

  //: in the order you would want them, with why each one matters
  const ROWS = [
    ['map', 'Map and log', 'Every room, and every line of every session.'],
    ['profiles', 'Characters', 'Names, triggers, aliases and line markers.'],
    ['scripts', 'Scripts', 'Python you have written; reloaded as you save.'],
    ['captures', 'Captures', 'Raw traffic, one folder per session.'],
    ['log', 'Client log', 'What it says when there is no console to say it to.'],
    ['data', 'All of the above', 'An update never touches this.'],
    ['program', 'The program', 'Replaced wholesale by an update.'],
  ];

  let shown = '';

  window.renderAbout = function (where) {
    if (!where) return;
    // Redrawn on every snapshot otherwise, which replaces whatever the cursor
    // is over -- the same trap that ate the Reconnect button.
    const key = JSON.stringify(where);
    if (key === shown) return;
    shown = key;

    $('about-name').textContent = `${where.name} ${where.version}`;
    const box = $('about-paths');
    box.replaceChildren();
    for (const [key2, label, why] of ROWS) {
      if (!where[key2]) continue;
      const row = document.createElement('div');
      row.className = 'frow';
      row.style.gridTemplateColumns = 'minmax(0,1fr)';

      const name = document.createElement('label');
      name.textContent = label;
      const path = document.createElement('code');
      path.className = 'about-path';
      path.textContent = where[key2];
      path.title = 'Click to select';
      // Selecting it is the point: the next thing you do with a path is paste
      // it somewhere.
      path.onclick = () => {
        const range = document.createRange();
        range.selectNodeContents(path);
        const pick = getSelection();
        pick.removeAllRanges();
        pick.addRange(range);
      };
      const note = document.createElement('p');
      note.className = 'fhint';
      note.textContent = why;

      row.append(name, path, note);
      box.append(row);
    }
  };
})();
