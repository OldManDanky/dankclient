/* Preferences that belong to the browser rather than to the character.

   Which panels are shown, how wide the terminal is, which channels are muted,
   what is rolled up: all about the screen in front of you, and a second window
   on a second monitor can reasonably want a different answer.  localStorage
   throws outright in some contexts -- a private window, a browser set to block
   site data -- so every read and write goes through here and a failure means
   "no preference", never a broken page.

   This used to own a floating panel frame as well: drag, resize, remember
   where you put it.  Nothing floats any more.  The map is docked in the
   sidebar and the messages across the top of the output, which is one fewer
   thing to place and one fewer thing sitting over the text. */

(function () {
  window.prefs = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : v;
      } catch (err) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (err) { /* private window: preferences just will not stick */ }
    },
  };
})();
