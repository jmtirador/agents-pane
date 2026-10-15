"""F9: Esc closes a dialog without Textual's 0.1 s input wake-up."""

import selectors
import time

from textual.drivers import linux_driver

from cockpit import quick_esc


def test_textuals_input_loop_wakes_every_20_ms(monkeypatch):
    monkeypatch.setattr(linux_driver, "selectors", selectors)
    quick_esc.install()
    selector = linux_driver.selectors.SelectSelector()
    assert linux_driver.selectors.EVENT_READ == selectors.EVENT_READ  # everything else is the real module
    started = time.perf_counter()
    selector.select(0.1)  # what the loop asks for; nothing to read
    assert time.perf_counter() - started < 0.06
    selector.close()
