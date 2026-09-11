"""Low level drawing helpers shared by every scene.

Anything that needs to be built once and blitted many times (gradients,
vignettes, glows) is cached by its arguments, because rebuilding a 1280x720
gradient every frame is the fastest way to lose sixty frames a second.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

import pygame

from . import theme

Color = Tuple[int, int, int]


# ------------------------------------------------------------------ shapes --
def rounded_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color,
    radius: int = 8,
    width: int = 0,
) -> None:
    pygame.draw.rect(surface, color, rect, width, border_radius=radius)


def panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fill: Color = theme.PANEL,
    edge: Optional[Color] = theme.PANEL_EDGE,
    radius: int = 12,
    alpha: int = 255,
    shadow: bool = True,
) -> None:
    """A standard rounded card/panel with an optional drop shadow."""
    if shadow:
        drop_shadow(surface, rect, radius=radius)
    if alpha >= 255:
        rounded_rect(surface, rect, fill, radius)
    else:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        rounded_rect(layer, layer.get_rect(), theme.with_alpha(fill, alpha), radius)
        surface.blit(layer, rect.topleft)
    if edge:
        rounded_rect(surface, rect, edge, radius, width=1)


def drop_shadow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int = 12,
    offset: Tuple[int, int] = (0, 4),
    spread: int = 6,
    alpha: int = 90,
) -> None:
    """A cheap soft shadow: a few nested translucent rounded rects."""
    layers = 4
    shadow = pygame.Surface(
        (rect.width + spread * 2, rect.height + spread * 2), pygame.SRCALPHA
    )
    for index in range(layers):
        grow = int(spread * (index + 1) / layers)
        band = pygame.Rect(
            spread - grow, spread - grow, rect.width + grow * 2, rect.height + grow * 2
        )
        rounded_rect(
            shadow,
            band,
            theme.with_alpha(theme.SHADOW, int(alpha / layers)),
            radius + grow,
        )
    surface.blit(shadow, (rect.x - spread + offset[0], rect.y - spread + offset[1]))


def glow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color: Color,
    radius: int = 12,
    spread: int = 14,
    alpha: int = 120,
) -> None:
    """A coloured halo used to highlight wins and the active seat."""
    layer = pygame.Surface(
        (rect.width + spread * 2, rect.height + spread * 2), pygame.SRCALPHA
    )
    steps = 5
    for index in range(steps):
        grow = int(spread * (steps - index) / steps)
        band = pygame.Rect(
            spread - grow, spread - grow, rect.width + grow * 2, rect.height + grow * 2
        )
        rounded_rect(
            layer, band, theme.with_alpha(color, int(alpha / steps)), radius + grow
        )
    surface.blit(layer, (rect.x - spread, rect.y - spread))


def circle(surface: pygame.Surface, center, radius: int, color, width: int = 0) -> None:
    pygame.draw.circle(surface, color, (int(center[0]), int(center[1])), int(radius), width)


# --------------------------------------------------------------- gradients --
@lru_cache(maxsize=64)
def _gradient(size: Tuple[int, int], top: Color, bottom: Color, horizontal: bool):
    width, height = size
    strip = pygame.Surface((1, height) if not horizontal else (width, 1))
    span = height if not horizontal else width
    for index in range(span):
        color = theme.mix(top, bottom, index / max(1, span - 1))
        if horizontal:
            strip.set_at((index, 0), color)
        else:
            strip.set_at((0, index), color)
    scaled = pygame.transform.smoothscale(strip, size)
    # convert() needs a display surface; without one the unconverted copy works.
    return scaled.convert() if pygame.display.get_surface() is not None else scaled


def gradient(
    surface: pygame.Surface,
    rect: pygame.Rect,
    top: Color,
    bottom: Color,
    horizontal: bool = False,
) -> None:
    surface.blit(_gradient((rect.width, rect.height), top, bottom, horizontal), rect.topleft)


@lru_cache(maxsize=16)
def _vignette(size: Tuple[int, int], strength: int):
    """A darkened border that focuses attention on the middle of the table."""
    width, height = size
    layer = pygame.Surface(size, pygame.SRCALPHA)
    steps = 28
    for index in range(steps):
        alpha = int(strength * (index / steps) ** 2.2)
        inset = int(min(width, height) * 0.5 * (1 - index / steps))
        rect = pygame.Rect(inset, inset, width - inset * 2, height - inset * 2)
        if rect.width <= 0 or rect.height <= 0:
            continue
        pygame.draw.rect(
            layer,
            theme.with_alpha(theme.SHADOW, alpha),
            rect,
            width=max(2, int(min(width, height) * 0.5 / steps) + 2),
            border_radius=inset,
        )
    return layer


def vignette(surface: pygame.Surface, strength: int = 150) -> None:
    surface.blit(_vignette(surface.get_size(), strength), (0, 0))


def felt_table(surface: pygame.Surface, rect: Optional[pygame.Rect] = None) -> None:
    """The default backdrop: a green felt gradient under a soft vignette."""
    rect = rect or surface.get_rect()
    gradient(surface, rect, theme.FELT_LIGHT, theme.FELT_DARK)


# -------------------------------------------------------------------- text --
def text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    message: str,
    position: Tuple[int, int],
    color: Color = theme.TEXT,
    anchor: str = "topleft",
    shadow: bool = False,
    shadow_color: Color = theme.SHADOW,
) -> pygame.Rect:
    """Draw ``message`` and return the rect it occupied.

    ``anchor`` is any ``pygame.Rect`` attribute name, so ``"center"``,
    ``"midtop"``, ``"topright"`` and friends all work.
    """
    if shadow:
        ghost = font.render(message, True, shadow_color)
        rect = ghost.get_rect(**{anchor: position})
        surface.blit(ghost, (rect.x + 2, rect.y + 2))
    glyphs = font.render(message, True, color)
    rect = glyphs.get_rect(**{anchor: position})
    surface.blit(glyphs, rect)
    return rect


def text_wrapped(
    surface: pygame.Surface,
    font: pygame.font.Font,
    message: str,
    rect: pygame.Rect,
    color: Color = theme.TEXT,
    line_spacing: int = 4,
) -> int:
    """Word-wrap ``message`` inside ``rect``; returns the height used."""
    words = message.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= rect.width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    y = rect.y
    for line in lines:
        surface.blit(font.render(line, True, color), (rect.x, y))
        y += font.get_height() + line_spacing
    return y - rect.y


def clear_cache() -> None:
    """Drop cached gradients and vignettes (see :func:`theme.clear_cache`)."""
    _gradient.cache_clear()
    _vignette.cache_clear()


def format_chips(amount: int) -> str:
    """Thousands-separated chip amounts, with a sign for deltas."""
    return f"{amount:,}"


def format_delta(amount: int) -> str:
    return f"+{amount:,}" if amount > 0 else f"{amount:,}"


def format_multiplier(value: float) -> str:
    return f"{value:.2f}x"
