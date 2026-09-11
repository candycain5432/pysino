"""Vector art for the slot machine symbols.

Like the playing cards these are drawn rather than loaded, and cached once per
size so a spinning reel costs nothing but blits.
"""

from __future__ import annotations

import math
from functools import lru_cache
import pygame

from . import theme
from ..games import slots as rules

CHERRY_RED = (204, 46, 62)
LEMON_YELLOW = (226, 194, 62)
BELL_GOLD = (232, 186, 72)
SHOE_STEEL = (176, 184, 192)
GEM_BLUE = (86, 196, 226)
CROWN_GOLD = (238, 198, 84)
SEVEN_RED = (214, 58, 62)
WILD_PURPLE = (150, 104, 222)
STAR_GOLD = (248, 214, 96)


def _star_points(centre, outer: float, inner: float, points: int = 5, rotation: float = -math.pi / 2):
    result = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = rotation + index * math.pi / points
        result.append((centre[0] + math.cos(angle) * radius,
                       centre[1] + math.sin(angle) * radius))
    return result


def _draw_cherry(surface: pygame.Surface, rect: pygame.Rect) -> None:
    radius = int(rect.width * 0.22)
    left = (rect.centerx - radius, rect.bottom - radius - 2)
    right = (rect.centerx + int(radius * 1.1), rect.bottom - int(radius * 1.4))
    stem_top = (rect.centerx + 2, rect.top + 4)
    pygame.draw.lines(surface, (78, 142, 62), False, [left, stem_top, right], 3)
    for centre in (left, right):
        pygame.draw.circle(surface, CHERRY_RED, centre, radius)
        pygame.draw.circle(surface, theme.darken(CHERRY_RED, 0.35), centre, radius, 2)
        pygame.draw.circle(surface, theme.lighten(CHERRY_RED, 0.45),
                           (centre[0] - radius // 3, centre[1] - radius // 3), max(2, radius // 4))


def _draw_lemon(surface: pygame.Surface, rect: pygame.Rect) -> None:
    body = rect.inflate(-int(rect.width * 0.18), -int(rect.height * 0.34))
    pygame.draw.ellipse(surface, LEMON_YELLOW, body)
    pygame.draw.ellipse(surface, theme.darken(LEMON_YELLOW, 0.35), body, 2)
    pygame.draw.ellipse(surface, theme.lighten(LEMON_YELLOW, 0.5),
                        pygame.Rect(body.x + 6, body.y + 5, body.width // 3, body.height // 4))


def _draw_bell(surface: pygame.Surface, rect: pygame.Rect) -> None:
    # The dome is a circle whose radius is half the body width, so the body has
    # to be narrow enough that the dome still fits inside the sprite.
    width = int(rect.width * 0.62)
    height = int(rect.height * 0.66)
    body = pygame.Rect(0, 0, width, height)
    body.center = (rect.centerx, rect.centery + int(rect.height * 0.04))
    radius = width // 2
    dome = (body.centerx, body.top + radius)

    pygame.draw.circle(surface, BELL_GOLD, dome, radius)
    pygame.draw.rect(surface, BELL_GOLD,
                     pygame.Rect(body.x, dome[1], width, body.bottom - dome[1] - 6))
    pygame.draw.rect(surface, BELL_GOLD,
                     pygame.Rect(body.x - 5, body.bottom - 9, width + 10, 8),
                     border_radius=4)
    pygame.draw.circle(surface, theme.darken(BELL_GOLD, 0.4),
                       (body.centerx, body.bottom + 1), max(2, width // 9))
    pygame.draw.rect(surface, theme.lighten(BELL_GOLD, 0.45),
                     pygame.Rect(body.x + 6, dome[1] - radius // 2, 4, body.height // 2))


def _draw_horseshoe(surface: pygame.Surface, rect: pygame.Rect) -> None:
    box = rect.inflate(-int(rect.width * 0.2), -int(rect.height * 0.24))
    thickness = max(4, box.width // 6)
    pygame.draw.arc(surface, SHOE_STEEL, box, math.pi * 0.05, math.pi * 0.95, thickness)
    for side in (box.left + thickness // 2, box.right - thickness // 2):
        pygame.draw.rect(surface, SHOE_STEEL,
                         pygame.Rect(side - thickness // 2, box.centery,
                                     thickness, box.height // 2), border_radius=2)
    for side in (box.left + thickness // 2, box.right - thickness // 2):
        pygame.draw.circle(surface, theme.darken(SHOE_STEEL, 0.45),
                           (side, box.bottom - 6), 3)


def _draw_diamond(surface: pygame.Surface, rect: pygame.Rect) -> None:
    box = rect.inflate(-int(rect.width * 0.22), -int(rect.height * 0.26))
    top = box.top + box.height // 4
    points = [
        (box.centerx, box.bottom),
        (box.left, top),
        (box.left + box.width // 4, box.top),
        (box.right - box.width // 4, box.top),
        (box.right, top),
    ]
    pygame.draw.polygon(surface, GEM_BLUE, points)
    pygame.draw.polygon(surface, theme.darken(GEM_BLUE, 0.4), points, 2)
    pygame.draw.line(surface, theme.lighten(GEM_BLUE, 0.55),
                     (box.left + box.width // 4, box.top), (box.centerx, box.bottom), 2)
    pygame.draw.line(surface, theme.lighten(GEM_BLUE, 0.35),
                     (box.left, top), (box.right, top), 2)


def _draw_crown(surface: pygame.Surface, rect: pygame.Rect) -> None:
    box = rect.inflate(-int(rect.width * 0.18), -int(rect.height * 0.34))
    points = [
        (box.left, box.bottom), (box.left, box.top + box.height // 3),
        (box.left + box.width // 4, box.centery),
        (box.centerx, box.top),
        (box.right - box.width // 4, box.centery),
        (box.right, box.top + box.height // 3), (box.right, box.bottom),
    ]
    pygame.draw.polygon(surface, CROWN_GOLD, points)
    pygame.draw.polygon(surface, theme.darken(CROWN_GOLD, 0.45), points, 2)
    pygame.draw.rect(surface, theme.darken(CROWN_GOLD, 0.2),
                     pygame.Rect(box.left, box.bottom - 6, box.width, 6))
    for x in (box.left + box.width // 4, box.centerx, box.right - box.width // 4):
        pygame.draw.circle(surface, CHERRY_RED, (x, box.bottom - 12), 3)


def _draw_seven(surface: pygame.Surface, rect: pygame.Rect) -> None:
    font = theme.fonts().get(max(18, int(rect.height * 0.78)), bold=True)
    glyphs = font.render("7", True, SEVEN_RED)
    shadow = font.render("7", True, theme.darken(SEVEN_RED, 0.5))
    centre = rect.center
    surface.blit(shadow, shadow.get_rect(center=(centre[0] + 2, centre[1] + 2)))
    surface.blit(glyphs, glyphs.get_rect(center=centre))


def _draw_wild(surface: pygame.Surface, rect: pygame.Rect) -> None:
    box = rect.inflate(-int(rect.width * 0.12), -int(rect.height * 0.3))
    pygame.draw.rect(surface, WILD_PURPLE, box, border_radius=6)
    pygame.draw.rect(surface, theme.lighten(WILD_PURPLE, 0.5), box, 2, border_radius=6)
    font = theme.fonts().get(max(11, int(box.height * 0.5)), bold=True)
    glyphs = font.render("WILD", True, theme.TEXT)
    if glyphs.get_width() > box.width - 6:
        glyphs = pygame.transform.smoothscale(
            glyphs, (box.width - 6, glyphs.get_height()))
    surface.blit(glyphs, glyphs.get_rect(center=box.center))


def _draw_scatter(surface: pygame.Surface, rect: pygame.Rect) -> None:
    centre = rect.center
    outer = min(rect.width, rect.height) * 0.42
    pygame.draw.polygon(surface, STAR_GOLD, _star_points(centre, outer, outer * 0.45))
    pygame.draw.polygon(surface, theme.darken(STAR_GOLD, 0.45),
                        _star_points(centre, outer, outer * 0.45), 2)
    pygame.draw.polygon(surface, theme.lighten(STAR_GOLD, 0.5),
                        _star_points(centre, outer * 0.4, outer * 0.18))


_PAINTERS = {
    rules.CHERRY: _draw_cherry,
    rules.LEMON: _draw_lemon,
    rules.BELL: _draw_bell,
    rules.HORSESHOE: _draw_horseshoe,
    rules.DIAMOND: _draw_diamond,
    rules.CROWN: _draw_crown,
    rules.SEVEN: _draw_seven,
    rules.WILD: _draw_wild,
    rules.SCATTER: _draw_scatter,
}


@lru_cache(maxsize=128)
def symbol_surface(symbol: str, width: int, height: int) -> pygame.Surface:
    """A transparent sprite of one slot symbol."""
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    painter = _PAINTERS.get(symbol)
    if painter:
        painter(surface, surface.get_rect())
    return surface


def draw_symbol(surface: pygame.Surface, symbol: str, rect: pygame.Rect) -> None:
    surface.blit(symbol_surface(symbol, rect.width, rect.height), rect.topleft)


def clear_cache() -> None:
    """Drop every cached symbol sprite."""
    symbol_surface.cache_clear()
