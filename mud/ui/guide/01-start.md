# Getting started

The first things to know: what is on the screen, where you type, and where everything else lives.

## The screen

- **The output** fills the middle. It is everything 3K sends, in its colours.
- **Messages**, across the top, keeps tells and channel lines where combat cannot scroll them away. See [The messages window](#messages).
- **The map**, top right, follows you. Click a room to walk there. See [The map and getting about](#map).
- **Session**, under the buttons, says who is logged in, whether MIP is live, and how many commands you have spent this minute (**APM**).
- **The Bot panel** runs a route or a bot. See [Routes and bots](#routes).
- **Your health and points** run along the bottom, above the box you type in.

## Typing commands

Type in the box at the bottom and press Enter. Anything you type goes to 3K, except:

- A line starting with `/` is for the client and never reaches 3K: `/go`, `/alias`, `/group`. `/help` lists them all, and so does [All client commands](#commands).
- A word you have made into an **alias** is turned into whatever the alias sends. See [Aliases](#aliases).

Several commands at once: separate them with `;`. `n;w;n;n;e;n` walks six rooms, and `kill rat;get all` does both. Each one goes where it would if typed alone, so an alias or a `/` command can be one of them. For a semicolon you mean to send, type `\;`. A line that starts with `/` keeps its semicolons, because they are part of that command.

Up and Down go back through what you have typed.

## Options

**Options**, top right, holds everything else: triggers, aliases and timers, routes and bots, layout, fonts, keys, sounds, your character's 3K settings and updates. **Find a setting**, at the top of it, searches every page. **Getting started** is the first page, and the first time a character logs in it opens by itself: work down it and press **Done**.

## Leaving

**Disconnect** stops the bots, saves everything and closes the connection. It does not send `quit`: you go link-dead, exactly as if the line had dropped. Closing the window does the same, then quits. If 3K drops you, the client logs you back in by itself.
