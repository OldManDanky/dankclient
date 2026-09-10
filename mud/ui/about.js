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
    // The installer itself, not the page it is on: the page is a detour
    // through a list of files to find the one that matters.  The release page
    // stays one click away for anyone who wants to know what changed.
    box.append(outside(release.url || release.page, 'Download the installer'));
    const notes = release.page && release.page !== release.url
      ? outside(release.page, 'what’s new') : null;
    if (notes) box.append(document.createTextNode(' ('), notes,
      document.createTextNode(')'));
    box.append(document.createTextNode(
      '. Installing it replaces the program and leaves your map, characters '
      + 'and triggers exactly where they are.'));
    if (window.options) window.options.count('about', 1);
  };

  /* A link that opens in the player's own browser.

     Only ever a GitHub address: the server checks too, and a javascript:
     address here would be a script running in the page that drives the
     character.  And not followed in the page: in app mode that opens inside
     the client's private profile, which would leave a downloaded installer in
     a browser window nobody recognises.  The server hands it to the browser
     they actually use, which downloads it the way it downloads anything. */
  function outside(address, text) {
    const link = document.createElement('a');
    const href = String(address || '');
    link.textContent = text;
    if (!href.startsWith('https://github.com/')) return link;
    link.href = href;
    link.rel = 'noreferrer';
    link.onclick = (e) => {
      e.preventDefault();
      if (window.ws && window.ws.readyState === 1) {
        window.ws.send(JSON.stringify({ t: 'open', url: href }));
      }
    };
    return link;
  }

  // The static link at the foot of the pane, for the same reason.
  const repo = $('about-repo');
  if (repo) repo.onclick = outside(repo.href, '').onclick;

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
      row.className = 'frow one';

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
