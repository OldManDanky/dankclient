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

  /* Whether there is a newer client than this one.

     Being told is the whole feature: it says what is out and links to it, and
     stops there. Fetching and running an installer on somebody's behalf is a
     different thing entirely, and not one to do while they are playing. */
  let told = '';

  window.renderRelease = function (release) {
    if (!release) return;
    const key = JSON.stringify(release);
    if (key === told) return;
    told = key;

    const box = $('about-release');
    box.replaceChildren();
    box.className = 'fhint';
    if (release.error) {
      box.textContent = 'Could not ask GitHub whether there is a newer one.';
      return;
    }
    if (!release.latest) {
      box.textContent = '';
      return;
    }
    if (!release.newer) {
      box.textContent = `This is the latest release (${release.latest}`
        + (release.when ? `, ${release.when}` : '') + ').';
      if (window.options) window.options.count('about', 0);
      return;
    }
    box.className = 'fhint new';
    box.append(document.createTextNode(
      `Version ${release.latest} is out — you have ${release.have}. `));
    const link = document.createElement('a');
    // Only ever a GitHub page.  The server checks too; a javascript: address
    // here would be a script running in the page that drives the character.
    const href = String(release.page || release.url || '');
    if (href.startsWith('https://github.com/')) link.href = href;
    link.target = '_blank';
    link.rel = 'noreferrer';
    link.textContent = 'Download the installer';
    box.append(link);
    box.append(document.createTextNode(
      '. Installing it replaces the program and leaves your map, characters '
      + 'and triggers exactly where they are.'));
    if (window.options) window.options.count('about', 1);
  };

  $('about-check').onclick = () => {
    $('about-release').textContent = 'asking GitHub…';
    told = '';
    if (window.ws && window.ws.readyState === 1) {
      window.ws.send(JSON.stringify({ t: 'update', op: 'client' }));
    }
  };

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
