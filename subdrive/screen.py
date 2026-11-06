"""Full-screen terminal: one screen at a time, arrow keys, nothing left behind when SubDrive closes.

Standard library only (msvcrt on Windows, termios on macOS and Linux). Without a real terminal
(tests, pipes) SubDrive keeps the plain line-by-line menu.
"""
from __future__ import annotations

import os
import sys
import time

UP, DOWN, LEFT, RIGHT, ENTER, ESC, BACKSPACE = "up", "down", "left", "right", "enter", "esc", "backspace"
RESIZE = "resize"          # the window changed size: the screen is drawn again
MIN_COLUMNS, MIN_ROWS = 100, 30  # a smaller window is enlarged when SubDrive opens (where the terminal allows it)


def available(stream=None) -> bool:
    stream = stream or sys.stdout
    try:
        return sys.stdin.isatty() and stream.isatty() and os.environ.get("TERM") != "dumb"
    except (AttributeError, ValueError):
        return False


def size(stream=None):
    """(columns, rows) of the window, or None when unknown."""
    try:
        return tuple(os.get_terminal_size((stream or sys.stdout).fileno()))
    except (AttributeError, ValueError, OSError):
        return None


class Screen:
    """Alternate screen buffer: the terminal's own history is restored on exit.

    Everything written since the last clear() is kept, so the screen can be drawn again from the
    top when the window changes size (the terminal does not rearrange it by itself)."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.page = []

    def __enter__(self):
        now = size(self.stream)
        if now and (now[0] < MIN_COLUMNS or now[1] < MIN_ROWS):
            self.stream.write("\033[8;%d;%dt" % (max(now[1], MIN_ROWS), max(now[0], MIN_COLUMNS)))
        self.write("\033[?1049h\033[H\033[2J")
        return self

    def __exit__(self, *exc):
        self.write("\033[?25h\033[?1049l")
        return False

    def write(self, text):
        self.stream.write(text); self.stream.flush()

    def record(self, text):
        self.page.append(text)

    def clear(self):
        self.page = []
        self.write("\033[H\033[2J\033[3J")

    def repaint(self, extra=""):
        """The current page again from the top, then `extra` (not kept), without flicker."""
        text = ("".join(self.page) + extra).replace("\n", "\033[K\n")
        self.write("\033[H" + text + "\033[K\033[J")

    def cursor(self, visible):
        self.write("\033[?25h" if visible else "\033[?25l")


class Recorder:
    """The stream the menu writes to: text goes to the terminal and is kept for repaint()."""

    def __init__(self, screen):
        self._screen, self._stream = screen, screen.stream

    def write(self, text):
        self._screen.record(text)
        return self._stream.write(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


# ---------------------------------------------------------------- keys

_seen = [None]


def _resized():
    now = size()
    if now is None:
        return False
    if _seen[0] is None:
        _seen[0] = now
    if now != _seen[0]:
        _seen[0] = now
        return True
    return False

def _windows_key():
    import msvcrt
    while not msvcrt.kbhit():
        if _resized():
            return RESIZE
        time.sleep(0.05)
    c = msvcrt.getwch()
    if c in ("\x00", "\xe0"):
        return {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT}.get(msvcrt.getwch(), "")
    return {"\r": ENTER, "\n": ENTER, "\x1b": ESC, "\x08": BACKSPACE, "\x03": "ctrl-c"}.get(c, c)


def _unix_key():
    import select, termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while not select.select([fd], [], [], 0.15)[0]:
            if _resized():
                return RESIZE
        c = os.read(fd, 1)
        if c == b"\x1b":
            if not select.select([fd], [], [], 0.05)[0]:
                return ESC
            seq = os.read(fd, 2)
            return {b"[A": UP, b"[B": DOWN, b"[D": LEFT, b"[C": RIGHT, b"OA": UP, b"OB": DOWN, b"OD": LEFT, b"OC": RIGHT}.get(seq, "")
        if c in (b"\r", b"\n"):
            return ENTER
        if c == b"\x03":
            return "ctrl-c"
        if c in (b"\x7f", b"\x08"):
            return BACKSPACE
        try:
            return c.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key():
    key = _windows_key() if os.name == "nt" else _unix_key()
    if key == "ctrl-c":
        raise KeyboardInterrupt
    return key


# ---------------------------------------------------------------- list selection

def select(draw, options, default=0, keys=read_key, back=True):
    """Arrow keys move, Enter chooses, Esc/← go back (None), digits 1-9 choose directly.

    draw(index) paints the screen with the option at `index` highlighted."""
    index = max(0, min(default or 0, len(options) - 1))
    while True:
        draw(index)
        key = keys()
        if key == RESIZE:
            continue
        if key == UP:
            index = (index - 1) % len(options)
        elif key == DOWN:
            index = (index + 1) % len(options)
        elif key in (ENTER, RIGHT):
            return index
        elif back and key in (ESC, LEFT, "0"):
            return None
        elif len(key) == 1 and key.isdigit() and 1 <= int(key) <= len(options):
            return int(key) - 1


def yes_no(keys=read_key, default=False, resized=None):
    """S/Y = sim, N = não, Enter = default, Esc = não."""
    while True:
        key = keys()
        if key == RESIZE and resized:
            resized()
        elif key == ENTER:
            return default
        if key in ("s", "S", "y", "Y"):
            return True
        if key in ("n", "N", ESC):
            return False
