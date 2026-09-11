"""Colour palette and font book.

Pysino ships no image or font assets: the whole look is drawn at runtime from
the values in this module, so the game is a pure ``pip install pygame-ce`` away
from running anywhere.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

Color = Tuple[int, int, int]

# ------------------------------------------------------------------ surfaces --
BG_DEEP: Color = (8, 16, 13)
BG_RAISED: Color = (16, 28, 23)
FELT: Color = (22, 92, 66)
FELT_DARK: Color = (12, 54, 39)
FELT_LIGHT: Color = (34, 118, 86)
WOOD: Color = (74, 47, 28)
WOOD_LIGHT: Color = (108, 71, 44)

PANEL: Color = (19, 34, 28)
PANEL_LIGHT: Color = (30, 50, 41)
PANEL_EDGE: Color = (46, 74, 61)

# --------------------------------------------------------------------- accent --
GOLD: Color = (212, 175, 55)
GOLD_DIM: Color = (138, 112, 40)
GOLD_BRIGHT: Color = (247, 224, 128)
SILVER: Color = (196, 202, 206)

# ----------------------------------------------------------------------- text --
TEXT: Color = (238, 234, 222)
TEXT_DIM: Color = (150, 164, 156)
TEXT_MUTED: Color = (104, 118, 110)
INK: Color = (16, 18, 20)

# --------------------------------------------------------------------- status --
WIN: Color = (94, 200, 120)
LOSE: Color = (226, 74, 68)
PUSH: Color = (216, 176, 72)
INFO: Color = (86, 154, 214)
WARN: Color = (232, 142, 58)
PURPLE: Color = (140, 104, 208)

CARD_FACE: Color = (248, 246, 240)
CARD_EDGE: Color = (206, 202, 190)
CARD_RED: Color = (196, 38, 46)
CARD_BLACK: Color = (28, 30, 34)
CARD_BACK: Color = (128, 30, 38)
CARD_BACK_DARK: Color = (84, 18, 26)

SHADOW: Color = (0, 0, 0)

#: Chip face colours, keyed by denomination.
CHIP_COLORS: Dict[int, Color] = {
    1: (238, 238, 234),
    5: (198, 52, 52),
    25: (38, 140, 86),
    100: (34, 36, 40),
    500: (118, 72, 176),
    2_500: (226, 158, 40),
}
CHIP_EDGE_COLORS: Dict[int, Color] = {
    1: (168, 168, 162),
    5: (128, 28, 28),
    25: (20, 92, 56),
    100: (86, 88, 94),
    500: (74, 42, 118),
    2_500: (154, 100, 20),
}


def chip_color(denomination: int) -> Color:
    return CHIP_COLORS.get(denomination, GOLD)


def chip_edge_color(denomination: int) -> Color:
    return CHIP_EDGE_COLORS.get(denomination, GOLD_DIM)


def with_alpha(color: Color, alpha: int) -> Tuple[int, int, int, int]:
    return (color[0], color[1], color[2], max(0, min(255, alpha)))


def lighten(color: Color, amount: float) -> Color:
    """Blend ``color`` towards white by ``amount`` (0-1)."""
    return tuple(min(255, int(channel + (255 - channel) * amount)) for channel in color)


def darken(color: Color, amount: float) -> Color:
    """Blend ``color`` towards black by ``amount`` (0-1)."""
    return tuple(max(0, int(channel * (1.0 - amount))) for channel in color)


def mix(a: Color, b: Color, t: float) -> Color:
    """Linear blend from ``a`` to ``b``."""
    t = max(0.0, min(1.0, t))
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# ------------------------------------------------------------------- fonts --
#: Tried in order; pygame's bundled font is the final fallback.
_SANS = "dejavusans,liberationsans,freesans,arial,helvetica,sans"
_MONO = "dejavusansmono,liberationmono,freemono,couriernew,monospace"


class FontBook:
    """Caches fonts by (size, weight, family) so scenes can ask freely."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, bool, bool], pygame.font.Font] = {}
        self._sans = pygame.font.match_font(_SANS)
        self._mono = pygame.font.match_font(_MONO)

    def get(self, size: int, bold: bool = False, mono: bool = False) -> pygame.font.Font:
        key = (size, bold, mono)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        path = self._mono if mono else self._sans
        if path:
            font = pygame.font.Font(path, size)
            font.set_bold(bold)
        else:
            # pygame's built-in font is already bold-ish; scale to compensate.
            font = pygame.font.Font(None, int(size * 1.15))
            font.set_bold(bold)
        self._cache[key] = font
        return font

    # Convenience sizes used throughout the UI.
    def tiny(self, bold: bool = False) -> pygame.font.Font:
        return self.get(13, bold)

    def small(self, bold: bool = False) -> pygame.font.Font:
        return self.get(16, bold)

    def body(self, bold: bool = False) -> pygame.font.Font:
        return self.get(20, bold)

    def large(self, bold: bool = False) -> pygame.font.Font:
        return self.get(28, bold)

    def title(self, bold: bool = True) -> pygame.font.Font:
        return self.get(40, bold)

    def huge(self, bold: bool = True) -> pygame.font.Font:
        return self.get(64, bold)


_fonts: FontBook | None = None


def fonts() -> FontBook:
    """The shared font book; created on first use, after ``pygame.font.init``."""
    global _fonts
    if not pygame.font.get_init():
        pygame.font.init()
        _fonts = None
    if _fonts is None:
        _fonts = FontBook()
    return _fonts


def clear_cache() -> None:
    """Forget every cached font.

    ``pygame.quit()`` invalidates existing ``Font`` objects without clearing
    the flag that says the font module is running, so anything holding one has
    to be told explicitly to let go.
    """
    global _fonts
    _fonts = None
