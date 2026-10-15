"""Esc without the lag (problems F9).

Textual takes a lone Esc as the Esc key once ESCDELAY ms pass with no more input, but its input loop only checks
when it wakes, every 0.1 s (textual 8.2.8, drivers/linux_driver.py: `selector.select(0.1)`). So Esc took ~0.16 s
to close a dialog whatever ESCDELAY said. Waking every 20 ms brings it to ~0.09 s; the idle list went from 2.5% to
3.2% of one core (measured on a private tmux server, 2026-10-14).
"""

import selectors

WAKE_S = 0.02


class QuickSelector(selectors.SelectSelector):
    def select(self, timeout=None):
        return super().select(WAKE_S if timeout is None else min(timeout, WAKE_S))


class _Selectors:
    """The selectors module as Textual's input loop sees it, with the quicker selector in it."""

    SelectSelector = QuickSelector

    def __getattr__(self, name):
        return getattr(selectors, name)


def install():
    """Before a Textual app runs. A Textual that no longer reads `selectors` this way is left alone."""
    try:
        from textual.drivers import linux_driver
    except ImportError:
        return
    if getattr(linux_driver, "selectors", None) is selectors:
        linux_driver.selectors = _Selectors()
