"""The welcome screen's words fit its box (64 columns, minus the "Tip: " prefix)."""

from cockpit.theme import PALETTES
from cockpit.welcome import TIPS, keys_line


def test_every_tip_fits_on_one_line():
    assert all(len("Tip: " + tip) <= 60 for tip in TIPS)


def test_the_way_back_has_one_name_everywhere():  # P5: it said "back to the list" here and "back to your sessions" in the bar
    assert "ctrl+] back to your sessions" in keys_line(PALETTES["neon"]).plain
    assert len(keys_line(PALETTES["neon"]).plain) <= 62
