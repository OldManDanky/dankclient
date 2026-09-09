"""Answering the two questions 3K asks before it lets you in.

The whole of the login is::

    <Entering 3Kingdoms.  Enter your character name or press enter to continue>
    Password:

Neither ends in a newline -- they are prompts -- so this watches a rolling
tail of the text rather than lines.  The tail is kept whether or not anybody
has chosen a character yet, because they usually have not: the connection is
made at startup and the browser takes a moment to appear, so by the time you
pick a name the question has already been asked and nothing is going to ask it
again.  Choosing looks at what is already on screen.

A password never reaches the log, the capture or the terminal.  It is the one
string in the client that must not be written down anywhere.
"""

from __future__ import annotations

#: Enough to hold either prompt whole, however the reads land.
TAIL = 512

ASKS_NAME = "enter your character name"
ASKS_PASSWORD = "password:"

#: what to answer next
NOTHING, NAME, PASSWORD, DONE = 0, 1, 2, 3


class Login:
    def __init__(self, send) -> None:
        #: send(text, secret=bool)
        self._send = send
        self.reset()

    def reset(self) -> None:
        """Back to knowing nothing, for a connection that has just been made.

        A new socket has never been asked anything, so a tail left over from
        the old one is a question that has already been answered -- and the
        name would go in twice.
        """
        self.name = ""
        self.password = ""
        self.stage = NOTHING
        self._tail = ""
        #: we answered the password ourselves, so the tail was cut past it
        self._answered = False

    @property
    def waiting(self) -> bool:
        """Is the MUD still asking who we are, and have we not answered?

        Decides whether choosing a character sends credentials or only loads
        their settings -- picking a character's aliases an hour into playing
        them should not type that name into the game.
        """
        if self.stage == DONE:
            return False
        return ASKS_NAME in self._tail or ASKS_PASSWORD in self._tail

    @property
    def done(self) -> bool:
        """Answered, or told not to.  Either way the screen has no more to do."""
        return self.stage == DONE

    @property
    def inside(self) -> bool:
        """Has the password question been answered, by whoever answered it?

        Which is the moment the client is allowed to speak.  Announce the
        handshake before it and ``3klient 40142~1.0`` is typed in as somebody's
        character name; wait for a greeting instead and you are guessing at
        wording -- the phrase this used to watch for was "Welcome", and 3K
        answers a reconnect with "3Kingdoms welcomes you back from linkdeath",
        which does not contain it.  Thirty-seven of thirty-eight logins in the
        captures on disk went that way, which is why the handshake had to be
        sent by hand.

        Read from the text rather than from our own state, so it is just as
        true for somebody who typed their name in themselves.
        """
        if self._answered:
            return True
        at = self._tail.rfind(ASKS_PASSWORD)
        # The prompt itself, then telnet's echo negotiation, then nothing until
        # the password goes in.  Anything after it is the MUD's answer.
        return at >= 0 and bool(self._tail[at + len(ASKS_PASSWORD):].strip())

    def feed(self, text: str) -> None:
        self._tail = (self._tail + text.lower())[-TAIL:]
        if ASKS_NAME in self._tail:
            # Asked again: a refused password puts you back at the start, and
            # anything we thought we knew about being inside is wrong.
            self._answered = False
        self._advance()

    def begin(self, name: str, password: str = "") -> None:
        self.name, self.password = name, password
        self.stage = NAME
        self._advance()

    def cancel(self) -> None:
        self.stage = DONE
        self.password = ""

    def _advance(self) -> None:
        if self.stage == NAME:
            at = self._tail.find(ASKS_NAME)
            if at >= 0:
                self._send(self.name, secret=False)
                self.stage = PASSWORD
                # Cut the tail at the question just answered rather than
                # emptying it.  The two prompts arrive within a few bytes of
                # each other and often in the same read: clearing throws the
                # second one away, and keeping it whole answers the first
                # twice.
                self._tail = self._tail[at + len(ASKS_NAME):]
        if self.stage == PASSWORD:
            at = self._tail.find(ASKS_PASSWORD)
            if at >= 0:
                self.stage = DONE
                if self.password:
                    self._send(self.password, secret=True)
                    self.password = ""
                    self._answered = True
                    self._tail = self._tail[at + len(ASKS_PASSWORD):]
                # With no password to send, the tail is left alone: somebody is
                # about to type one, and the answer coming back is the only
                # sign of it we will get.
