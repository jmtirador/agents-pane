"""The looks: one palette drives the list, the welcome screen, tmux's divider and the key bar.

Direction A (picked 2026-10-08): the terminal paints the background (decision 0002), the frame is one
quiet gray, and color is for meaning. Each look has one loud color, used only for "waiting for you";
the looks change accents, never the background. `base` is a hex copy of his terminal's gray (#282c34,
Ghostty's default), used only to blend card and dim colors, because Textual can't blend an ANSI color.

Textual is imported only where a Textual app needs it, so a viewer (cockpit/viewer.py) for a session starts without it.
"""

from dataclasses import dataclass

from . import store

BASE = "#282c34"
# a session waiting for him: its text pulses in this orange, the same in every theme (Pepe, 2026-10-09: "just change
# the text font color to orange or flashing orange"); deeper than the finch stripe's #ff9e64 so the two don't blur
ATTENTION = "#ff7b00"


@dataclass(frozen=True)
class Palette:
    name: str
    label: str  # what he sees: "Neon", "Mission control", "Tokyo night"
    brand: str  # the theme's own color: where the welcome screen's wordmark starts, and its first dot in the theme menu
    work: str
    done: str
    fail: str
    quiet: str  # working but silent for a while
    key: str  # key letters in the bar and in hints
    needs: str = ATTENTION  # the one loud color: only a session waiting for him (its text pulses), never a fill
    base: str = BASE
    card: str = "#2c313c"  # a card, one step up from the terminal's gray
    sel: str = "#3a4150"  # the card the cursor is on
    text: str = "#dcdfe4"
    text2: str = "#abb2bf"
    text3: str = "#7f848e"  # labels and hints
    line: str = "#5c6370"  # the divider, the line over the keys, and every box

    @property
    def theme_name(self):
        return f"agents-{self.name}"

    def variables(self):
        return {"ap-text2": self.text2, "ap-dim": self.text3, "ap-line": self.line, "ap-key": self.key}

    def textual(self):
        from textual.theme import Theme

        return Theme(
            name=self.theme_name,
            primary=self.key,
            secondary=self.key,
            accent=self.needs,
            foreground=self.text,
            background=self.base,
            surface=self.card,
            panel=self.sel,
            success=self.done,
            warning=self.quiet,
            error=self.fail,
            dark=True,
            variables=self.variables(),
        )


PALETTES = {
    "neon": Palette(name="neon", label="Neon", brand="#ff4fd8", work="#5fd7ff", done="#7cffb2",
                    fail="#ff5f87", quiet="#e5c07b", key="#5fd7ff"),
    "mission": Palette(name="mission", label="Mission control", brand="#ffb000", work="#2dd4bf",
                       done="#a3e635", fail="#ff5555", quiet="#d19a66", key="#2dd4bf"),
    "tokyo": Palette(name="tokyo", label="Tokyo night", brand="#ff007c", work="#7aa2f7", done="#9ece6a",
                     fail="#f7768e", quiet="#e0af68", key="#7dcfff"),
}

ORDER = ["neon", "mission", "tokyo"]

# A color per project, from the folder a session runs in: decided once, never guessed from words.
# None of them is a look's loud color, so a stripe never reads as "waiting for you".
PROJECT_COLORS = [
    ("Projects/finch", "#ff9e64"),
    ("Projects/brain", "#bb9af7"),
    ("Projects/ai-wiki", "#bb9af7"),
    ("Projects/san-jose-foods", "#e0af68"),
    ("Projects/agents-pane", "#94e2d5"),
]
SPARE_COLORS = ["#7dcfff", "#9ece6a", "#f7768e", "#2ac3de", "#e0af68", "#c0caf5"]
HOME_COLOR = "#9aa5ce"


def current():
    """The look he last picked."""
    return PALETTES.get(store.load()["theme"], PALETTES["neon"])


def install(app, palette):
    """Give a Textual app all three looks and switch it to this one."""
    for p in PALETTES.values():
        app.register_theme(p.textual())
    app.theme = palette.theme_name


def mix(a, b, share):
    """A color share of the way from a to b."""
    pa, pb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#" + "".join(f"{round(x + (y - x) * share):02x}" for x, y in zip(pa, pb, strict=True))
