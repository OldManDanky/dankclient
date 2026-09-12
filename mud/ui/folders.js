/* Folders for a list that has outgrown being a list.
 *
 * A folder is not a thing: it is the prefix its items carry, so "chaos" and
 * "chaos/dungeon" exist exactly as long as something is filed there.  That is
 * why there is no folder to create on its own and no empty one to tidy up --
 * naming one while filing the first item into it is the whole of creating it.
 *
 * Both lists that needed this hold different things, so this renders neither:
 * it takes the items, asks each for its folder path, and calls back for the
 * card.  Rules already grouped themselves one level deep; routes had nothing
 * and 3kdb gives you 141 of them.
 *
 * Collapsed folders are remembered per list in localStorage, which is a
 * per-viewer convenience and nothing more: it can throw (a private window,
 * blocked site data), so every read and write is guarded and the list draws
 * correctly with none of it.
 */
(function () {
  /* Which folders are folded away, per list, held here for the life of the
     page.  localStorage only makes it survive a reload: it was the store
     itself at first, and then folding did nothing at all where storage is
     blocked -- every redraw read an empty set back.  In memory it works
     regardless; the mirror is the convenience. */
  const folded = new Map();

  function open_set(key) {
    if (!folded.has(key)) {
      let was = [];
      try {
        was = JSON.parse(localStorage.getItem('folds:' + key) || '[]');
      } catch (e) {
        was = [];
      }
      folded.set(key, new Set(Array.isArray(was) ? was : []));
    }
    return folded.get(key);
  }

  function remember(key, shut) {
    try {
      localStorage.setItem('folds:' + key, JSON.stringify([...shut]));
    } catch (e) {
      /* nothing to do about it, and nothing depends on it */
    }
  }

  /* items -> a tree of { name, path, kids: Map, items: [] }.  Ordered by
     folder name, then by whatever order the items arrived in, which is the
     order the list had before folders existed. */
  function build(items, folderOf) {
    const root = { name: '', path: '', kids: new Map(), items: [] };
    for (const item of items) {
      const path = (folderOf(item) || '').trim();
      let at = root;
      if (path) {
        for (const part of path.split('/')) {
          const key = part.toLowerCase();
          if (!at.kids.has(key)) {
            at.kids.set(key, {
              name: part,
              path: at.path ? at.path + '/' + part : part,
              kids: new Map(),
              items: [],
            });
          }
          at = at.kids.get(key);
        }
      }
      at.items.push(item);
    }
    return root;
  }

  function countIn(node) {
    let n = node.items.length;
    for (const kid of node.kids.values()) n += countIn(kid);
    return n;
  }

  window.folderTree = function (opts) {
    const { key, items, folderOf, card, onRename } = opts;
    const shut = open_set(key);
    const out = [];

    function row(node, depth) {
      const head = document.createElement('div');
      head.className = 'folder';
      head.style.setProperty('--depth', depth);
      const closed = shut.has(node.path.toLowerCase());
      head.dataset.closed = closed ? '1' : '';

      const twist = document.createElement('button');
      twist.type = 'button';
      twist.className = 'twist';
      twist.textContent = closed ? '▸' : '▾';
      twist.setAttribute('aria-expanded', closed ? 'false' : 'true');
      twist.title = closed ? 'Show what is in here' : 'Fold this away';
      twist.onclick = function () {
        const at = node.path.toLowerCase();
        if (shut.has(at)) shut.delete(at); else shut.add(at);
        remember(key, shut);
        if (opts.redraw) opts.redraw();
      };

      const name = document.createElement('b');
      name.textContent = node.name;
      const count = document.createElement('span');
      count.className = 'n';
      const n = countIn(node);
      // A list that measures its folders differently says so itself: rules
      // count what is switched on, which is the useful number there.
      count.textContent = opts.count ? opts.count(node, n)
        : n === 1 ? '1 item' : n + ' items';
      head.append(twist, name, count);

      // A list may want its own folder-wide action: rules switch a whole
      // group on and off, as `/group party on` does.
      for (const extra of (opts.actions ? opts.actions(node) : [])) {
        if (extra) head.append(extra);
      }
      if (onRename) {
        const ren = document.createElement('button');
        ren.type = 'button';
        ren.textContent = 'Rename';
        ren.title = 'Renames this folder and everything under it. '
          + 'Emptying the name files them at the top.';
        ren.onclick = function () {
          const want = window.prompt('Folder name (a / makes another level, '
            + 'an empty name files them at the top):', node.path);
          if (want !== null && want !== node.path) onRename(node.path, want);
        };
        head.append(ren);
      }
      return head;
    }

    function walk(node, depth) {
      const kids = [...node.kids.values()]
        .sort((a, b) => a.name.localeCompare(b.name));
      for (const kid of kids) {
        out.push(row(kid, depth));
        if (!shut.has(kid.path.toLowerCase())) walk(kid, depth + 1);
      }
      for (const item of node.items) {
        const el = card(item);
        if (el) {
          el.style.setProperty('--depth', depth);
          if (depth) el.classList.add('filed');
          out.push(el);
        }
      }
    }

    walk(build(items, folderOf), 0);
    return out;
  };
})();
