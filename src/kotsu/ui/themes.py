"""Screen themes (D37): Cotton Candy light and night. Only colors and ornaments, no business
rules."""

from __future__ import annotations

from dataclasses import dataclass

from textual.theme import Theme as TextualTheme


@dataclass(frozen=True)
class Theme:
    name: str  # identifier saved in theme.toml
    label: str
    dark: bool
    background: str
    surface: str
    panel: str
    text: str
    highlight: str  # pink: title, header, cursor
    secondary: str  # blue: labels at the top
    warning: str  # gold: little face
    income: str
    expense: str
    neutral: str
    # Ornaments.
    bullet: str = "♡"
    zeroed: str = "zzz… zeroed"
    bar_full: str = "♥"
    bar_empty: str = "·"
    happy: str = "(◕‿◕)♡"
    sad: str = "(；ω；)"

    def to_textual(self) -> TextualTheme:
        return TextualTheme(
            name=self.name,
            primary=self.highlight,
            secondary=self.secondary,
            accent=self.warning,
            background=self.background,
            surface=self.surface,
            panel=self.panel,
            foreground=self.text,
            success=self.income,
            error=self.expense,
            warning=self.warning,
            dark=self.dark,
        )


COTTON_CANDY_NIGHT = Theme(
    name="cotton-candy-night", label="Cotton Candy night", dark=True,
    background="#1d1424", surface="#291b33", panel="#41274f", text="#ffe9f4",
    highlight="#ff7fb8", secondary="#8fb3ff", warning="#ffd27a",
    income="#86efc0", expense="#ff7a9e", neutral="#9a7fa8",
)  # fmt: skip

COTTON_CANDY_LIGHT = Theme(
    name="cotton-candy-light", label="Cotton Candy light", dark=False,
    background="#fff5fa", surface="#ffeaf4", panel="#ffd6e8", text="#5a3a5e",
    highlight="#e0509a", secondary="#4f74c7", warning="#b87400",
    income="#1f9d6b", expense="#d6336c", neutral="#8f6f8c",
)  # fmt: skip

THEMES = (COTTON_CANDY_NIGHT, COTTON_CANDY_LIGHT)
DEFAULT = COTTON_CANDY_NIGHT

# Names saved by versions before the English rename.
_LEGACY_NAMES = {"algodao-noite": COTTON_CANDY_NIGHT.name, "algodao-claro": COTTON_CANDY_LIGHT.name}


def theme_by_name(name: str | None) -> Theme:
    """Theme with a known name; anything else falls back to the default."""
    name = _LEGACY_NAMES.get(name, name)
    return next((t for t in THEMES if t.name == name), DEFAULT)


def next_theme(current: Theme) -> Theme:
    return THEMES[(THEMES.index(current) + 1) % len(THEMES)]
