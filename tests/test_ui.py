"""Static checks on the browser code.

There is no JS runtime here, but the failure that matters most is cheap to
catch statically: a lookup for an element that does not exist returns null,
and assigning a handler to it throws at load time, which aborts the whole
module and silently kills every other handler in it.  That is exactly how the
rule panel's buttons stopped working -- a form rewrite dropped two elements
that unrelated code still referenced.
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "mud" / "ui"


def html() -> str:
    return (UI / "index.html").read_text()


def scripts() -> dict[str, str]:
    return {p.name: p.read_text() for p in UI.glob("*.js")}


def test_every_element_lookup_resolves():
    ids = set(re.findall(r'id="([\w-]+)"', html()))
    problems = {}
    for name, js in scripts().items():
        used = set(re.findall(r"\$\('([\w-]+)'\)", js))
        missing = sorted(used - ids)
        if missing:
            problems[name] = missing
    assert not problems, f"lookups with no matching id: {problems}"


def test_no_duplicate_ids():
    found = re.findall(r'id="([\w-]+)"', html())
    dupes = sorted({i for i in found if found.count(i) > 1})
    assert not dupes, f"duplicate ids: {dupes}"


def test_hidden_is_not_outranked_by_a_display_rule():
    """An id selector setting display beats [hidden], so toggling .hidden
    silently does nothing -- how the flyout became uncloseable."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    assert re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", style)


def test_scripts_are_referenced_by_the_page():
    page = html()
    for name in scripts():
        assert f'src="{name}"' in page, f"{name} is never loaded"


def test_braces_balance():
    """Crude, but catches a truncated or mis-merged edit."""
    def strip(src: str) -> str:
        out, i, n, prev = [], 0, len(src), ""
        while i < n:
            c, two = src[i], src[i:i + 2]
            if two == "//":
                i = src.find("\n", i)
                i = n if i < 0 else i
                continue
            if two == "/*":
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "\"'`":
                q = c
                i += 1
                while i < n:
                    if src[i] == "\\":
                        i += 2
                        continue
                    if src[i] == q:
                        i += 1
                        break
                    i += 1
                out.append('""')
                prev = '"'
                continue
            if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%~^<>"):
                i += 1
                in_class = False
                while i < n:
                    if src[i] == "\\":
                        i += 2
                        continue
                    if src[i] == "[":
                        in_class = True
                    elif src[i] == "]":
                        in_class = False
                    elif src[i] == "/" and not in_class:
                        i += 1
                        break
                    elif src[i] == "\n":
                        break
                    i += 1
                out.append("R")
                prev = "R"
                continue
            out.append(c)
            if not c.isspace():
                prev = c
            i += 1
        return "".join(out)

    for name, js in scripts().items():
        s = strip(js)
        for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
            assert s.count(a) == s.count(b), f"{name}: {a}{b} unbalanced"


def test_layout_rules_survive():
    """The column that holds the terminal and the input bar.

    A careless CSS splice once removed #term's rule entirely: the terminal
    collapsed to its content height and dragged the input bar halfway up the
    window.  Nothing else in the page hints that these are load-bearing.
    """
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]

    required = {
        "body": ("display:flex", "height:100vh"),
        "main": ("flex:1", "flex-direction:column", "position:relative"),
        "#out": ("flex:1", "min-height:0", "flex-direction:column"),
        "#term": ("flex:1", "min-height:0"),
        ".dock": ("flex:none", "flex-direction:column"),
    }
    for selector, needles in required.items():
        rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", style)
        assert rule, f"no rule for {selector}"
        body = rule.group(1).replace(" ", "").replace("\n", "")
        for needle in needles:
            assert needle.replace(" ", "") in body, \
                f"{selector} lost {needle!r}"


def test_the_terminal_cursor_stays_hidden():
    """The terminal takes no input; a cursor there is misleading."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    assert "xterm-cursor" in style, "cursor-hiding rules are gone"


def test_the_preference_store_loads_before_its_users():
    """Every panel reads window.prefs at load time.  A script tag in the
    wrong order leaves it undefined and they die silently."""
    page = html()
    order = re.findall(r'<script src="([\w.-]+)"', page)
    for name, js in scripts().items():
        if name != "prefs.js" and "window.prefs" in js:
            assert order.index("prefs.js") < order.index(name), name


def test_panels_look_up_the_parts_they_expect():
    """Each panel queries its own frame; a renamed class here is the same
    silent null that killed the rule buttons."""
    page = html()
    for cls in (".cm-body", ".cm-toggle", ".cm-filters", ".cm-count",
                ".map-body", ".map-where"):
        assert f'class="{cls[1:]}"' in page, f"no element carries {cls}"


def test_the_map_panel_is_reachable_and_drawn():
    js = scripts()["map.js"]
    assert "getElementById('mapmon')" in js
    assert 'id="mapmon"' in html()
    # the server sends the map inside the state snapshot
    assert "window.renderMap(s.map)" in scripts()["app.js"]


def test_nothing_floats_over_the_output_any_more():
    """Two message panels and a map that could each be dragged anywhere meant
    three things to place and three things in the way of the text."""
    page, js = html(), scripts()
    assert 'id="monitors"' not in page
    for name, src in js.items():
        assert "dockPanel" not in src, f"{name} still wants a floating frame"
    assert "position:absolute" not in re.search(
        r"\.dock\{([^}]*)\}", page[page.index("<style>"):]).group(1)


def test_the_map_does_not_reach_for_the_dock_it_is_inside():
    js = scripts()["map.js"]
    assert "dock." not in js


def test_the_map_body_cannot_collapse_to_nothing():
    """Its canvas is absolutely positioned and so lends it no height.  With
    min-height:0 the body collapses and the map draws, perfectly, into a box
    a pixel tall -- the label beside it renders and the picture does not."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    # every rule that sizes it, not just the first one in the file
    rules = re.findall(r"[^{}]*\.map-body\{([^}]*)\}", style)
    assert rules, "nothing sizes .map-body"
    for body in rules:
        if "height" not in body:
            continue
        floor = re.search(r"min-height:\s*(\d+)px", body)
        assert floor and int(floor.group(1)) > 0, f"no floor in: {body}"


def test_the_map_checks_for_null_and_undefined_together():
    """An older server sends no `centre` at all.  `=== null` lets undefined
    through, and the map then drew a blank panel and called it an empty map."""
    js = scripts()["map.js"]
    assert "centre === null" not in js
    assert "centre == null" in js


def test_the_routes_panel_is_wired_up():
    page = html()
    js = scripts()["routes.js"]
    for element in ("route-list", "route-form", "r-name", "r-path", "r-targets",
                    "r-loop", "r-rest", "r-id", "r-setup", "r-start",
                    "r-polite", "route-error", "route-stop-all", "r-new",
                    "route-back", "route-cancel"):
        assert f'id="{element}"' in page, f"{element} is not in the page"
        assert f"'{element}'" in js, f"{element} is never used"
    assert "window.handleRoutes(m)" in scripts()["app.js"]


def test_options_is_grouped_by_what_you_are_looking_for():
    """Automation, the screen, the character, the client -- and nobody looks
    for sounds under "Panels", so they have a tab of their own."""
    page = html()
    rail = page[page.index('<nav id="opt-tabs">'):page.index("</nav>")]
    groups = re.findall(r'<div class="opt-group">([^<]+)</div>', rail)
    assert groups == ["Automation", "Interface", "Game", "Client"], groups
    for tab in ("keyboard", "sounds", "panels", "fonts", "settings"):
        assert f'data-tab="{tab}"' in rail, tab
    interface = rail[rail.index("Interface"):rail.index("Game")]
    for tab in ("panels", "fonts", "keyboard", "sounds"):
        assert f'data-tab="{tab}"' in interface, tab
    # A pane is a <section>, which the sidebar styles as a box.
    assert "background:none;border:0;border-radius:0;padding:0" in page


def test_every_pane_says_what_it_is_for_in_a_line_or_two():
    """The why is in docs/DESIGN.md.  A settings pane that opens with an
    essay is one people stop reading."""
    page = html()
    for intro in re.findall(r'<div class="opt-head">\s*<div>\s*<h4[^>]*>[^<]*</h4>\s*'
                            r'<p[^>]*>(.*?)</p>', page, re.S):
        words = len(re.sub(r"<[^>]+>", "", intro).split())
        assert words <= 40, f"{words} words: {intro[:60]!r}"


def test_the_title_says_the_version_and_counts_tells_while_away():
    js = scripts()["app.js"]
    assert "${s.where.name} ${s.where.version}" in js
    assert "noteTell(m.d)" in js and "d.from_me" in js
    assert "addEventListener('focus', seen)" in js


def test_new_output_below_is_offered_and_cleared():
    """A tester's "the screen froze" was output landing out of sight."""
    page, js = html(), scripts()["app.js"]
    assert 'id="term-new"' in page
    assert "term.onLineFeed" in js and "below.hidden = false" in js
    send = js[js.index("function send(text, echo)"):]
    assert "$('term-new').hidden = true" in send[:send.index("\n}")]


def test_options_has_a_search_for_every_setting():
    page, js = html(), scripts()["optfind.js"]
    assert 'id="opt-find"' in page and 'id="opt-results"' in page
    assert '<script src="optfind.js">' in page
    rail = page[page.index('<nav id="opt-tabs">'):page.index("</nav>")]
    assert rail.index('id="opt-find"') < rail.index("opt-group"), "top of the rail"
    for part in ("querySelectorAll('.opt-pane')", "'.frow'", "'.fhint'",
                 "e.stopPropagation()"):
        assert part in js, part


def test_every_tab_has_a_pane_and_every_pane_a_tab():
    """A tab with no pane shows an empty panel and no error anywhere."""
    page = html()
    tabs = set(re.findall(r'data-tab="([\w-]+)"', page))
    panes = set(re.findall(r'data-pane="([\w-]+)"', page))
    assert tabs == panes, f"tabs {tabs ^ panes} have nothing on the other side"
    assert tabs, "no tabs at all"


def test_each_rule_kind_has_somewhere_to_be_listed():
    """rules.js files a rule under its kind; a missing list is a silent null
    and the whole module dies with it."""
    page, js = html(), scripts()["rules.js"]
    for kind in ("trigger", "alias", "event", "watch"):
        assert f'id="list-{kind}"' in page, f"nowhere to list a {kind}"
        assert f'data-tab="{kind}"' in page, f"no tab for {kind}"
    assert "window.refreshRules" in js


def test_only_one_module_opens_and_closes_the_panel():
    """Three flyouts that could each be open over the other became one.  The
    frame belongs to options.js; a second module reaching for `hidden` on it
    is how they got out of step in the first place."""
    js = scripts()
    assert "window.options" in js["options.js"]
    frame = ("options", "opt-panes", "opt-tabs", "opt-test", "rule-editor",
             "route-editor")
    for name in ("rules.js", "routes.js"):
        for el in frame:
            assert f"$('{el}')" not in js[name], \
                f"{name} reaches past the frame for {el}"
        assert "window.options.editor(" in js[name], \
            f"{name} never asks the frame to show its editor"


def test_the_prefix_button_shows_before_it_sends():
    """Thirteen settings going to somebody's character is not a one-click
    action; the first press asks the client to print them."""
    js = scripts()["app.js"]
    assert 'id="set-prefixes"' in html()
    assert "'/prefixes'" in js and "' set'" in js


def test_the_map_lays_out_only_what_fits():
    """A couple of hundred rooms in a panel holding sixty filled it with long
    lines running to rooms flung wherever a cell was free -- which said
    nothing true about the geography and buried the part that did."""
    js = scripts()["map.js"]
    assert "function layout(map, halfX, halfY)" in js
    assert "layout(state," in js               # bounded by the drawing area


def test_the_map_does_not_draw_lines_to_rooms_that_are_not_next_door():
    """Every room in the Tree of Life has a 'turnaway' back to its entrance.
    Drawn as lines, twenty-one of those bury the straight run the area
    actually is."""
    js = scripts()["map.js"]
    assert "const near = Math.max(Math.abs(a.x - b.x)" in js
    assert "drift(from)" in js       # and a chain of portals lays out straight


def test_the_login_screen_is_wired_up():
    page, js = html(), scripts()["login.js"]
    for element in ("login", "char-list", "char-form", "c-name", "c-host",
                    "c-port", "c-password", "c-remember", "c-note",
                    "char-add", "char-cancel", "char-error", "login-skip",
                    "open-login", "login-state", "char-form-title",
                    "c-password-hint"):
        assert f'id="{element}"' in page, f"{element} is not in the page"
        assert f"'{element}'" in js, f"{element} is never used"
    assert "window.renderWho(s.who)" in scripts()["app.js"]
    assert "window.handleLogin(m)" in scripts()["app.js"]


def test_the_login_screen_never_shows_a_saved_password():
    """The server sends has_password, never the password.  A field filled in
    from the snapshot is a password on the wire and in the DOM."""
    js = scripts()["login.js"]
    assert "has_password" in js
    assert "char.password" not in js, "the browser reads a password it is not sent"


def test_the_login_screen_sits_over_everything():
    """Until somebody says who is playing, the client does not know whose
    triggers to load, and loading the wrong ones is worse than loading none."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    def z(sel):
        rule = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", style)
        assert rule, f"no rule for {sel}"
        m = re.search(r"z-index:\s*(\d+)", rule.group(1))
        return int(m.group(1)) if m else 0
    assert z("#login") > z("#options")


def test_the_map_is_docked_in_the_sidebar_not_over_the_terminal():
    """It is the panel you glance at most, and one you have to place is one
    that is in the way of the text underneath it."""
    page = html()
    assert page.index('<aside id="side">') < page.index('id="mapmon"')
    assert '<aside id="mapmon" class="dock">' in page


def test_the_docked_map_puts_back_what_the_sidebar_would_give_it():
    """#mapmon is an <aside> inside the sidebar, so the sidebar's own width
    and padding land on it -- 330px and a 12px frame inside a 232px column."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    dock = re.search(r"\.dock\{([^}]*)\}", style).group(1).replace(" ", "")
    for needle in ("width:auto", "padding:0", "gap:0"):
        assert needle in dock, f".dock does not put back {needle}"


def test_the_room_panel_is_off_until_it_is_asked_for():
    """It lists everything in the room with a button per action, which is
    worth having and is not worth a third of the sidebar when it is not."""
    page, js = html(), scripts()["panels.js"]
    assert '<section id="roompanel" hidden>' in page
    assert "roompanel" in js and "on: false" in js
    # and last, so it is the panel you consult rather than the one you watch
    assert page.index('id="roompanel"') > page.index('id="combat"')


def test_the_sidebar_reads_top_to_bottom():
    """Three buttons, then the session, then the map, then the bot.

    The buttons are the things you reach for without looking -- where the
    settings are, what is running, and out.  The session -- who is playing,
    whether MIP is live -- moved above the map by request: it is the line you
    check before trusting anything below it.
    """
    page = html()
    order = [page.index(needle) for needle in (
        '<aside id="side">',
        'id="side-acts"',
        'id="session"',
        'id="mapmon"',
        'id="botpanel"',
    )]
    assert order == sorted(order), order


def test_the_three_buttons_are_in_reaching_order():
    """Disconnect last, and away from the other two: it is the one press in
    the sidebar you cannot take back by pressing it again."""
    page = html()
    row = page[page.index('id="side-acts"'):page.index('id="mapmon"')]
    assert row.index('id="open-options"') < row.index('id="open-bots"') \
        < row.index('id="hangup"'), row
    assert 'class="danger"' in row


def test_the_disconnected_banner_is_markup_not_rebuilt():
    """It redraws on every push -- ten times a second while a countdown is
    running.  A button built in render() is a different button by the time the
    mouse comes back up, so the click lands on nothing."""
    page, js = html(), scripts()["app.js"]
    assert 'id="link-again"' in page, "the button must outlive a redraw"
    assert 'id="link-why"' in page
    banner = js[js.index("const box = $('link')"):]
    banner = banner[:banner.index("\n  const mip")]
    assert "replaceChildren" not in banner, "the banner rebuilds itself"
    assert "createElement" not in banner, "the banner rebuilds itself"


def test_the_character_list_is_not_rebuilt_under_the_cursor():
    """Same trap, same screen: renderWho runs on every snapshot."""
    js = scripts()["login.js"]
    assert "JSON.stringify(state)" in js and "=== last" in js


def test_the_way_back_is_the_login_screen():
    """After a hang-up, "who is playing" and "how do I get back on" are the
    same question, so one screen answers both."""
    assert "window.openLogin" in scripts()["login.js"]
    assert "window.openLogin()" in scripts()["app.js"]


def test_disconnecting_does_not_immediately_reconnect():
    """The whole point of the button.  A session that comes back two seconds
    after you press Disconnect is a session with a broken button."""
    js = scripts()["app.js"]
    assert "t: 'link'" in js and "'hangup'" in js
    assert "confirm(" in js, "a mis-click leaves you link-dead in the open"


def test_session_sits_above_the_map_and_says_only_what_it_should():
    """Who is playing, whether MIP is live, APM, and the MUD's uptime -- above
    the map.  The bots' own pause note is in the Bot panel, with the bots."""
    page = html()
    side = page[page.index('<aside id="side">'):page.index("</aside>\n\n<div id=\"login\"")]
    order = [side.index(f'id="{i}"') for i in ("side-acts", "session", "mapmon",
                                                  "botpanel")]
    assert order == sorted(order), "buttons, Session, map, Bot"
    session = side[side.index('id="session"'):side.index('id="mapmon"')]
    for element in ("status", "link", "open-login", "mip", "apm", "chrome"):
        assert f'id="{element}"' in session, element
    assert 'id="deadman-note"' not in session
    bot = side[side.index('id="botpanel"'):]
    assert 'id="deadman-note"' in bot
    js = scripts()["app.js"]
    assert "'MIP live'" in js and "mip.title" in js, "short, detail on hover"


def test_a_running_route_says_which_step_of_how_many():
    """"Walking" on its own does not tell you whether to wait for it or go and
    do something else.  Said in the sidebar's Bot panel, with its buttons."""
    page, js = html(), scripts()["bots.js"]
    for element in ("botpanel", "bot-now", "bot-name", "bot-step", "bot-bar",
                    "bot-note", "bot-start", "bot-pause", "bot-stop",
                    "bot-find", "bot-found"):
        assert f'id="{element}"' in page, f"{element} is not in the page"
    for element in ("bot-name", "bot-step", "bot-bar", "bot-note", "bot-find"):
        assert f"'{element}'" in js, f"{element} is never filled in"
    assert "step_count" in js and "steps_taken" in js
    assert '<script src="bots.js">' in page
    assert "renderBotPanel(routes, walk)" in scripts()["routes.js"]
    assert "id: 'botpanel'" in scripts()["panels.js"]


def test_the_map_cannot_be_dragged_or_scaled():
    """It is a thing you glance at, not a thing you operate.  A map you can
    drag off centre or zoom out of is one that needs putting back before it
    can be read."""
    page, js = html(), scripts()["map.js"]
    for gone in ("zoom", "wheel", "pointerdown", "pointermove", "setPointerCapture"):
        body = "\n".join(l for l in js.split("\n")
                         if not l.strip().startswith(("//", "*", "/*")))
        assert gone not in body, f"the map still handles {gone}"
    style = page[page.index("<style>"):page.index("</style>")]
    dock = re.search(r"\.dock\{([^}]*)\}", style).group(1)
    assert "resize" not in dock, "the frame can still be dragged bigger"
    size = re.search(r"#mapmon\{([^}]*)\}", style).group(1)
    assert "height" in size, "the map has no size of its own to keep"


def test_the_terminal_is_held_to_a_readable_measure():
    """3k.org draws to about eighty columns; on a full-screen window the rest
    is empty, with the text huddled down the left of it."""
    js = scripts()["app.js"]
    assert "window.setTerminalWidth" in js
    assert re.search(r"DEFAULT_COLS = \d+", js)
    assert "'term-cols'" in scripts()["panels.js"]
    assert 'id="term-cols"' in html()


def test_refit_does_not_resize_the_box_it_measures():
    """It is watched by a ResizeObserver, so clearing the cap to measure and
    setting it again is two changes that call it straight back -- for ever.
    A column's width is measured once and kept instead: it is a property of
    the font, and the font does not change with the window."""
    js = scripts()["app.js"]
    watched = re.search(
        r"new ResizeObserver\(\(\) => refit\(\)\)\.observe\(\$\('(\w+)'\)\)", js)
    assert watched, "nothing refits the terminal when its box changes"
    assert f'id="{watched.group(1)}"' in html()

    body = js[js.index("function refit()"):]
    body = body[:body.index("\n}")]
    assert "if (!perCol) measure();" in body, "the measurement is not cached"
    assert body.count("measure()") == 2, "refit measures more than it must"


def test_every_outer_edge_shares_one_gutter():
    """The terminal's first line, the vitals strip, the input box and the
    docked map should start on the same lines, not within a couple of pixels
    of each other."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    for selector in ("#term", "#bar", "aside", "#vitals"):
        rule = re.search(re.escape(selector) + r"\{([^}]*)\}", style).group(1)
        assert "var(--gut)" in rule, f"{selector} sets its own gutter"
    assert re.search(r"--gut:\s*\d+px", style), "no gutter to share"


def test_the_messages_window_carries_every_kind():
    """MIP separates personal traffic from channels and Portal drew the same
    line, but that is the MUD's idea of the difference rather than the
    reader's.  One window, with `tell` as one more tag."""
    page, js = html(), scripts()["chat.js"]
    assert 'id="msgmon"' in page
    assert 'id="tellmon"' not in page and 'id="chatmon"' not in page
    assert "window.seedMessages" in js and "window.pushMessage" in js
    # tells still get a speaker column; BAB often omits the name
    assert "cm-who" in js


def test_the_tags_come_from_the_traffic():
    """Guild and clan channels differ per character, so a fixed list is
    somebody else's list -- and a channel nobody has spoken on is a tag with
    nothing behind it."""
    js = scripts()["chat.js"]
    assert "function tags()" in js
    assert "new Set(messages.map" in js


def test_muting_a_tag_does_not_collapse_the_window():
    """The header collapses on a click and the tags sit under it."""
    js = scripts()["chat.js"]
    assert "e.stopPropagation()" in js


def test_the_two_scrollbars_land_on_one_line():
    """The messages window sits over the terminal, so its scrollbar and the
    terminal's are read as a pair whether or not they were meant to be."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]

    def rule(sel):
        return re.search(re.escape(sel) + r"\{([^}]*)\}", style).group(1)

    # the border sits outside the terminal's text column, so the content box
    # inside it lands on the same line
    assert "calc(var(--gut) - 1px)" in rule("#msgmon")
    # and nothing between that edge and the scrollbar
    body = rule(".cm-body")
    assert re.search(r"padding:[^;]*\s0(px)?\s", body + " "), \
        f".cm-body pads its scrollbar away from the edge: {body}"
    # xterm always reserves the gutter; a panel that only sometimes reserves
    # one does not line up with it
    assert "overflow-y:scroll" in body


def test_every_scrollbar_on_the_page_is_the_same_one():
    """The terminal's belongs to xterm and lives in its own stylesheet; these
    properties inherit, so setting them on the root reaches it too."""
    page = html()
    style = page[page.index("<style>"):page.index("</style>")]
    root = re.search(r":root\{([^}]*)\}", style).group(1)
    assert "scrollbar-width" in root and "scrollbar-color" in root
    assert "::-webkit-scrollbar-thumb" in style          # older browsers


def test_the_map_is_drawn_around_you():
    """Where you are is the middle of the panel, with nothing that can move
    it.  It looks otherwise when an area runs off in one direction and leaves
    the rest of the panel empty, which is most of them -- and all of them the
    moment you walk in -- so your room also gets a ring."""
    js = scripts()["map.js"]
    assert "const cx = box.width / 2;" in js
    assert "const cy = box.height / 2;" in js
    assert "placed.set(map.centre, { x: 0, y: 0," in js
    assert "ctx.arc(x, y, dot, 0, Math.PI * 2);" in js
    assert "drawn`" not in js, "the room counter is still in the corner"


def test_one_search_box_filters_whichever_list_is_showing():
    """Six boxes -- one per tab -- would be six places to look for the same
    thing."""
    page, js = html(), scripts()
    assert 'id="opt-search"' in page
    assert "$('opt-search')" in js["options.js"]
    for name in ("rules.js", "routes.js"):
        assert "window.options.query()" in js[name], f"{name} ignores the search"
    # and it redraws from what the browser has rather than asking again
    assert "window.renderRules = render;" in js["rules.js"]
    assert "window.renderRoutes = render;" in js["routes.js"]
    assert "refilter" in js["options.js"]


def test_a_search_does_not_survive_a_tab_change():
    """A list that looks empty for a reason you have already stopped thinking
    about is worse than no search at all."""
    js = scripts()["options.js"]
    body = js[js.index("function show(name)"):]
    body = body[:body.index("\n  }")]
    assert "$('opt-search').value = '';" in body


def test_searching_looks_at_what_a_rule_does_as_well():
    """Half of what you remember about a rule is what it does: "the one that
    quaffs" is a search for the command, and the pattern that fires it is the
    part you have forgotten."""
    js = scripts()["rules.js"]
    hay = js[js.index("function haystack(r)"):]
    hay = hay[:hay.index("\n  }")]
    for field in ("r.pattern", "r.name", "a.text", "r.event", "r.watch_field"):
        assert field in hay, f"a search cannot find {field}"
    # a route's path, for the same reason -- with sixty-seven imported the
    # thing you remember is often a step rather than a name
    assert "r.path" in scripts()["routes.js"]


def test_an_empty_list_says_whether_it_is_empty_or_filtered():
    page, js = html(), scripts()
    assert "data-none=" in page and "content:attr(data-empty)" in page
    for name in ("rules.js", "routes.js"):
        assert "dataset.empty" in js[name] and "dataset.none" in js[name]


def test_the_timers_tab_is_wired_up():
    page, js = html(), scripts()
    assert 'data-tab="timer"' in page and 'data-pane="timer"' in page
    assert 'id="list-timer"' in page and 'id="f-every"' in page
    assert "'list-timer'" in js["rules.js"] and "'f-every'" in js["rules.js"]


def test_a_timer_cannot_be_tested_against_a_line():
    """It does not match anything; it just comes round."""
    js = scripts()["options.js"]
    assert "const TESTABLE" in js
    body = js[js.index("const TESTABLE"):]
    assert "'timer'" not in body[:body.index("]")]


def test_the_client_can_say_where_it_keeps_things():
    """Installed, it says none of this: it lands somewhere without announcing
    it, and afterwards there is a Start Menu entry and no way to find out what
    it did. "Where is my map" gets asked more than once."""
    page, js = html(), scripts()["about.js"]
    assert 'data-pane="about"' in page and 'data-tab="about"' in page
    for element in ("about-name", "about-paths", "about-repo"):
        assert f'id="{element}"' in page, element
    for key in ("map", "profiles", "captures", "log", "data", "program"):
        assert f"'{key}'" in js, key


def test_the_numpad_hears_its_keys_before_the_command_box():
    """With NumLock off, numpad 8 is also ArrowUp and 9 is PageUp.  The
    command box acted on them first: history moved as the character walked,
    and 9 scrolled the terminal up out of sight of everything new."""
    js = scripts()
    assert "addEventListener('keydown', window.numpadKey, true)" in js["numpad.js"]
    send = js["app.js"][js["app.js"].index("function send(text, echo)"):]
    assert "term.scrollToBottom()" in send[:send.index("\n}")]


def test_one_column_rows_are_a_class_not_an_inline_width():
    """Panels -> Show and About drew crooked: they set the row to one column
    inline, and the form row's own rules still pushed the label right and
    everything else into a column that was not there."""
    page, js = html(), scripts()
    assert ".frow.one>label:first-child{grid-column:1;justify-self:start" in page
    for name in ("panels.js", "about.js"):
        assert "'frow one'" in js[name], name
    for name, body in js.items():
        assert "gridTemplateColumns" not in body, name


def test_the_about_pane_is_not_rebuilt_under_the_cursor():
    """Third time this trap has come up, so it is checked now."""
    js = scripts()["about.js"]
    assert "JSON.stringify(where)" in js and "=== shown" in js


def test_there_is_an_icon_and_it_is_a_real_one():
    """Windows shows a generic executable box for anything without one, and a
    program that looks like every other unlabelled program is one people
    lose."""
    import struct

    path = UI / "icon.ico"
    assert path.exists(), "run tools/make_icon.py"
    body = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", body[:6])
    assert (reserved, kind) == (0, 1), "not an ICO header"
    assert count >= 4, "Windows asks for several sizes"

    seen, at = [], 6
    for _ in range(count):
        w, h, _c, _r, _p, bits, size, offset = struct.unpack(
            "<BBBBHHII", body[at:at + 16])
        at += 16
        seen.append(w or 256)
        assert bits == 32, "needs an alpha channel to have a rounded corner"
        assert body[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"
        assert offset + size <= len(body), "an entry points past the end"
    assert 16 in seen and 256 in seen, f"16 is the taskbar, 256 is Explorer: {seen}"


def test_the_page_offers_the_icon_as_well_as_the_inline_one():
    """The tab can have an SVG; the app-mode window and the taskbar want a
    raster."""
    page = html()
    assert 'href="icon.ico"' in page
    assert 'href="data:image/svg+xml,' in page


def test_the_commands_are_findable_without_already_knowing_about_help():
    """They lived only in the terminal, which meant the only way to learn what
    the client does was to already know that /help existed."""
    page, js = html(), scripts()["help.js"]
    assert 'data-tab="help"' in page and 'data-pane="help"' in page
    assert 'id="help-groups"' in page
    assert "t: 'help'" in js
    # clicking one loads it into the input rather than running it: they take
    # arguments, and "/go " with the cursor after it is the useful thing
    assert "getElementById('cmd')" in js


def test_every_command_is_in_a_group():
    """A flat list of thirty-five is a list nobody reads, and a command that
    falls out of the grouping is one nobody finds."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mud.commands import HELP

    seen = [verb for _t, _b, rows in HELP for verb, _d in rows]
    assert len(seen) == len(set(seen)), "a command listed twice"
    assert len(seen) > 30
    for title, _blurb, rows in HELP:
        assert rows, f"{title} is empty"
        assert title[0].isupper()
