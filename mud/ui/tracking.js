/* The Combat tracking panel: what a tracking pack keeps count of.

   Each pack says one thing -- a label, a number, perhaps a rate, a row or
   two of detail, a few chips -- and this draws it as a block: the number big
   enough to read at a glance in a fight, everything else quieter beneath it.
   The panel is there only while some pack has something to say, and rolled
   up its heading keeps the counts. */

(function () {
  const $ = (id) => document.getElementById(id);

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function block(item) {
    const box = el('div', 'trk');
    if (typeof item === 'string') {
      // A pack that still says a line of text.
      box.append(el('div', 'trk-line', item));
      return box;
    }
    const head = el('div', 'trk-head');
    head.append(el('span', 'trk-label', item.label || ''));
    if (item.note) head.append(el('span', 'trk-note', item.note));
    box.append(head);
    const value = String(item.value === undefined ? '' : item.value);
    box.append(el('div', 'trk-value' + (value === '0' ? ' zero' : ''), value));
    for (const [key, text, bits] of item.rows || []) {
      const row = el('div', 'trk-row');
      row.append(el('span', 'trk-key', key), el('span', 'trk-text', text));
      if (bits && bits.length) {
        const line = el('div', 'trk-bits');
        for (const bit of bits) line.append(el('span', 'trk-bit', bit));
        row.append(line);
      }
      box.append(row);
    }
    if (item.chips && item.chips.length) {
      const chips = el('div', 'trk-chips');
      for (const [name, n] of item.chips) {
        const chip = el('span', 'trk-chip');
        chip.append(el('span', 'trk-chip-name', name), el('span', 'trk-chip-n', n));
        chips.append(chip);
      }
      box.append(chips);
    }
    return box;
  }

  function summary(list) {
    return list.map((i) => (typeof i === 'string' ? i : `${i.label} ${i.value}`))
      .join('  ·  ');
  }

  let last = null;
  window.renderTracking = function (items) {
    const list = Array.isArray(items) ? items.filter(Boolean) : [];
    // The snapshot arrives several times a second; redraw only on a change.
    const key = JSON.stringify(list);
    if (key === last) return;
    last = key;
    const box = $('pack-status');
    if (!box) return;
    box.replaceChildren(...list.map(block));
    $('trackpanel').hidden = !list.length;
    $('track-sum').textContent = summary(list);
  };
})();
