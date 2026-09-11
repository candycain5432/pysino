"""Procedurally drawn playing cards, chips and slot symbols.

Suit pips are built from circles and polygons rather than font glyphs so the
cards look identical on a machine with no particular fonts installed.  Every
finished sprite is cached, so a table full of cards costs a handful of blits.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

import pygame

from . import theme
from .cards import Card

CARD_SIZE = (96, 134)
CARD_RADIUS = 8

#: Where the pips sit on a number card, in fractions of the inner face.
PIP_LAYOUTS: Dict[int, List[Tuple[float, float]]] = {
    2: [(0.50, 0.13), (0.50, 0.87)],
    3: [(0.50, 0.13), (0.50, 0.50), (0.50, 0.87)],
    4: [(0.27, 0.13), (0.73, 0.13), (0.27, 0.87), (0.73, 0.87)],
    5: [(0.27, 0.13), (0.73, 0.13), (0.50, 0.50), (0.27, 0.87), (0.73, 0.87)],
    6: [(0.27, 0.13), (0.73, 0.13), (0.27, 0.50), (0.73, 0.50), (0.27, 0.87), (0.73, 0.87)],
    7: [(0.27, 0.13), (0.73, 0.13), (0.50, 0.31), (0.27, 0.50), (0.73, 0.50),
        (0.27, 0.87), (0.73, 0.87)],
    8: [(0.27, 0.13), (0.73, 0.13), (0.50, 0.31), (0.27, 0.50), (0.73, 0.50),
        (0.50, 0.69), (0.27, 0.87), (0.73, 0.87)],
    9: [(0.27, 0.13), (0.73, 0.13), (0.27, 0.37), (0.73, 0.37), (0.50, 0.50),
        (0.27, 0.63), (0.73, 0.63), (0.27, 0.87), (0.73, 0.87)],
    10: [(0.27, 0.13), (0.73, 0.13), (0.50, 0.25), (0.27, 0.37), (0.73, 0.37),
         (0.27, 0.63), (0.73, 0.63), (0.50, 0.75), (0.27, 0.87), (0.73, 0.87)],
}


# ----------------------------------------------------------------- suit art --
def draw_heart(surface: pygame.Surface, rect: pygame.Rect, color) -> None:
    radius = rect.width // 4
    left = (rect.centerx - radius, rect.top + radius)
    right = (rect.centerx + radius, rect.top + radius)
    pygame.draw.circle(surface, color, left, radius)
    pygame.draw.circle(surface, color, right, radius)
    pygame.draw.polygon(
        surface,
        color,
        [
            (rect.left, rect.top + radius),
            (rect.right, rect.top + radius),
            (rect.centerx, rect.bottom),
        ],
    )


def draw_diamond(surface: pygame.Surface, rect: pygame.Rect, color) -> None:
    pygame.draw.polygon(
        surface,
        color,
        [
            (rect.centerx, rect.top),
            (rect.right, rect.centery),
            (rect.centerx, rect.bottom),
            (rect.left, rect.centery),
        ],
    )


def draw_spade(surface: pygame.Surface, rect: pygame.Rect, color) -> None:
    radius = rect.width // 4
    body = rect.bottom - rect.height // 5
    pygame.draw.polygon(
        surface,
        color,
        [
            (rect.centerx, rect.top),
            (rect.right, body - radius),
            (rect.left, body - radius),
        ],
    )
    pygame.draw.circle(surface, color, (rect.centerx - radius, body - radius), radius)
    pygame.draw.circle(surface, color, (rect.centerx + radius, body - radius), radius)
    stem = rect.width // 6
    pygame.draw.polygon(
        surface,
        color,
        [
            (rect.centerx - stem, rect.bottom),
            (rect.centerx + stem, rect.bottom),
            (rect.centerx + stem // 3, body - radius),
            (rect.centerx - stem // 3, body - radius),
        ],
    )


def draw_club(surface: pygame.Surface, rect: pygame.Rect, color) -> None:
    radius = rect.width // 4
    top = (rect.centerx, rect.top + radius)
    body = rect.bottom - rect.height // 5
    pygame.draw.circle(surface, color, top, radius)
    pygame.draw.circle(surface, color, (rect.centerx - radius, body - radius), radius)
    pygame.draw.circle(surface, color, (rect.centerx + radius, body - radius), radius)
    stem = rect.width // 6
    pygame.draw.polygon(
        surface,
        color,
        [
            (rect.centerx - stem, rect.bottom),
            (rect.centerx + stem, rect.bottom),
            (rect.centerx + stem // 3, body - radius),
            (rect.centerx - stem // 3, body - radius),
        ],
    )


_SUIT_PAINTERS = {
    "h": draw_heart,
    "d": draw_diamond,
    "s": draw_spade,
    "c": draw_club,
}


def draw_pip(surface: pygame.Surface, rect: pygame.Rect, suit: str, color) -> None:
    """Paint a suit symbol filling ``rect``."""
    _SUIT_PAINTERS[suit](surface, rect, color)


@lru_cache(maxsize=64)
def pip_surface(suit: str, size: int, color: Tuple[int, int, int]) -> pygame.Surface:
    """A standalone pip, handy for scoreboards and bet chips."""
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    draw_pip(surface, surface.get_rect(), suit, color)
    return surface


# --------------------------------------------------------------- the cards --
@lru_cache(maxsize=256)
def _face(rank: int, suit: str, width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    rect = surface.get_rect()
    color = theme.CARD_RED if suit in ("h", "d") else theme.CARD_BLACK

    pygame.draw.rect(surface, theme.CARD_FACE, rect, border_radius=CARD_RADIUS)
    pygame.draw.rect(surface, theme.CARD_EDGE, rect, 1, border_radius=CARD_RADIUS)

    from .cards import RANK_NAMES

    label = RANK_NAMES[rank]
    corner_size = max(11, int(height * 0.135))
    font = theme.fonts().get(corner_size, bold=True)
    glyphs = font.render(label, True, color)
    inset = max(4, int(width * 0.06))
    surface.blit(glyphs, (inset, inset - 1))

    corner_pip = max(7, int(width * 0.12))
    pip_box = pygame.Rect(0, 0, corner_pip, corner_pip)
    pip_box.midtop = (inset + glyphs.get_width() // 2, inset + glyphs.get_height() - 1)
    draw_pip(surface, pip_box, suit, color)

    # The bottom-right corner is the top-left rotated half a turn.
    corner = pygame.Surface((glyphs.get_width() + 4, pip_box.bottom - inset + 2), pygame.SRCALPHA)
    corner.blit(glyphs, (0, 0))
    box = pygame.Rect(0, 0, corner_pip, corner_pip)
    box.midtop = (glyphs.get_width() // 2, glyphs.get_height() - 1)
    draw_pip(corner, box, suit, color)
    surface.blit(pygame.transform.rotate(corner, 180),
                 (width - corner.get_width() - inset, height - corner.get_height() - inset))

    if rank == 14:
        big = pygame.Rect(0, 0, int(width * 0.44), int(width * 0.44))
        big.center = rect.center
        draw_pip(surface, big, suit, color)
    elif rank >= 11:
        # Kept clear of the corner indices so the frame never collides with them.
        court = rect.inflate(-int(width * 0.40), -int(height * 0.34))
        _draw_court(surface, court, label, suit, color)
    else:
        inner = rect.inflate(-int(width * 0.34), -int(height * 0.16))
        pip_size = max(9, int(width * 0.19))
        for fx, fy in PIP_LAYOUTS[rank]:
            box = pygame.Rect(0, 0, pip_size, pip_size)
            box.center = (inner.x + int(inner.width * fx), inner.y + int(inner.height * fy))
            draw_pip(surface, box, suit, color)
    return surface


def _draw_court(surface: pygame.Surface, frame: pygame.Rect, label: str,
                suit: str, color) -> None:
    """A simple framed panel for the jack, queen and king."""
    pygame.draw.rect(surface, theme.mix(theme.CARD_FACE, color, 0.10), frame, border_radius=4)
    pygame.draw.rect(surface, color, frame, 1, border_radius=4)

    letter = theme.fonts().get(max(20, int(frame.height * 0.42)), bold=True)
    glyphs = letter.render(label, True, color)
    surface.blit(glyphs, glyphs.get_rect(center=(frame.centerx, frame.centery - frame.height * 0.18)))

    crown = pygame.Rect(0, 0, int(frame.width * 0.42), int(frame.width * 0.42))
    crown.center = (frame.centerx, int(frame.centery + frame.height * 0.24))
    draw_pip(surface, crown, suit, color)


@lru_cache(maxsize=8)
def _back(width: int, height: int) -> pygame.Surface:
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    rect = surface.get_rect()
    pygame.draw.rect(surface, theme.CARD_FACE, rect, border_radius=CARD_RADIUS)
    inner = rect.inflate(-6, -6)
    pygame.draw.rect(surface, theme.CARD_BACK, inner, border_radius=CARD_RADIUS - 2)

    # A lattice of diamonds, clipped to the inner panel.
    step = max(8, width // 8)
    lattice = pygame.Surface(inner.size, pygame.SRCALPHA)
    for y in range(0, inner.height + step, step):
        for x in range(0, inner.width + step, step):
            offset = step // 2 if (y // step) % 2 else 0
            points = [
                (x + offset, y - step // 3),
                (x + offset + step // 3, y),
                (x + offset, y + step // 3),
                (x + offset - step // 3, y),
            ]
            pygame.draw.polygon(lattice, theme.CARD_BACK_DARK, points)
    surface.blit(lattice, inner.topleft)
    pygame.draw.rect(surface, theme.GOLD_DIM, inner, 1, border_radius=CARD_RADIUS - 2)
    pygame.draw.rect(surface, theme.CARD_EDGE, rect, 1, border_radius=CARD_RADIUS)
    return surface


def card_surface(card: Card, size: Tuple[int, int] = CARD_SIZE) -> pygame.Surface:
    """A face-up card sprite."""
    return _face(card.rank, card.suit, int(size[0]), int(size[1]))


def card_back(size: Tuple[int, int] = CARD_SIZE) -> pygame.Surface:
    """A face-down card sprite."""
    return _back(int(size[0]), int(size[1]))


def draw_card(
    surface: pygame.Surface,
    card: Card | None,
    position: Tuple[int, int],
    size: Tuple[int, int] = CARD_SIZE,
    face_up: bool = True,
    shadow: bool = True,
    highlight=None,
) -> pygame.Rect:
    """Blit a card (or its back when ``card`` is ``None``) and return its rect."""
    sprite = card_surface(card, size) if (face_up and card is not None) else card_back(size)
    rect = sprite.get_rect(topleft=(int(position[0]), int(position[1])))
    if shadow:
        from . import render

        render.drop_shadow(surface, rect, radius=CARD_RADIUS, spread=5, alpha=110)
    if highlight:
        from . import render

        render.glow(surface, rect, highlight, radius=CARD_RADIUS, spread=10, alpha=150)
    surface.blit(sprite, rect)
    return rect


def flipped_card(
    card: Card | None,
    progress: float,
    size: Tuple[int, int] = CARD_SIZE,
    face_up_at_end: bool = True,
) -> Tuple[pygame.Surface, int]:
    """A card mid-flip.

    ``progress`` runs 0-1; the sprite is squashed horizontally and swaps face at
    the halfway point.  Returns the surface and how far to shift it right to
    keep the card centred.
    """
    progress = max(0.0, min(1.0, progress))
    showing_back = progress < 0.5
    if face_up_at_end:
        sprite = card_back(size) if showing_back else card_surface(card, size)
    else:
        sprite = card_surface(card, size) if showing_back else card_back(size)
    squeeze = abs(1.0 - 2.0 * progress)
    width = max(1, int(size[0] * squeeze))
    scaled = pygame.transform.smoothscale(sprite, (width, size[1]))
    return scaled, (size[0] - width) // 2


# -------------------------------------------------------------------- chips --
@lru_cache(maxsize=64)
def chip_surface(denomination: int, radius: int = 22) -> pygame.Surface:
    """A casino chip with edge spots and its value printed in the middle."""
    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (radius, radius)
    face = theme.chip_color(denomination)
    edge = theme.chip_edge_color(denomination)

    pygame.draw.circle(surface, edge, center, radius)
    # Six light wedges around the rim, the classic chip pattern.
    for index in range(6):
        start = math.radians(index * 60)
        points = [center]
        for step in range(9):
            angle = start + math.radians(step * 30 / 8)
            points.append(
                (center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius)
            )
        pygame.draw.polygon(surface, theme.lighten(face, 0.55), points)

    pygame.draw.circle(surface, face, center, int(radius * 0.78))
    pygame.draw.circle(surface, theme.darken(face, 0.35), center, int(radius * 0.78), 2)
    pygame.draw.circle(surface, theme.lighten(face, 0.18), center, int(radius * 0.60))

    label = _chip_label(denomination)
    font = theme.fonts().get(max(9, int(radius * 0.62)), bold=True)
    ink = theme.INK if sum(face) > 330 else theme.TEXT
    glyphs = font.render(label, True, ink)
    surface.blit(glyphs, glyphs.get_rect(center=center))
    return surface


def _chip_label(denomination: int) -> str:
    if denomination >= 1_000:
        thousands = denomination / 1_000
        return f"{thousands:.0f}K" if thousands == int(thousands) else f"{thousands:.1f}K"
    return str(denomination)


def draw_chip_stack(
    surface: pygame.Surface,
    position: Tuple[int, int],
    denomination: int,
    count: int,
    radius: int = 20,
    spacing: int = 5,
) -> pygame.Rect:
    """A little stack of chips, drawn bottom-up from ``position``."""
    chip = chip_surface(denomination, radius)
    count = max(1, min(count, 12))
    x, y = position
    for index in range(count):
        surface.blit(chip, (x - radius, y - radius - index * spacing))
    return pygame.Rect(x - radius, y - radius - (count - 1) * spacing, radius * 2,
                       radius * 2 + (count - 1) * spacing)


def clear_cache() -> None:
    """Drop every cached card, pip and chip sprite."""
    _face.cache_clear()
    _back.cache_clear()
    pip_surface.cache_clear()
    chip_surface.cache_clear()


def chips_for_amount(amount: int, denominations: Sequence[int]) -> List[Tuple[int, int]]:
    """Break ``amount`` into ``(denomination, count)`` pairs, largest first."""
    result: List[Tuple[int, int]] = []
    remaining = int(amount)
    for denomination in sorted(denominations, reverse=True):
        if remaining <= 0:
            break
        count, remaining = divmod(remaining, denomination)
        if count:
            result.append((denomination, count))
    return result
