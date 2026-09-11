"""European roulette with a full betting layout."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..games import roulette as rules
from .base import GameScene, draw_result_banner

WHEEL_CENTRE = (212, 374)
WHEEL_RADIUS = 112

GRID_X, GRID_Y = 470, 150
CELL_W, CELL_H = 56, 54
ZERO_W = 46
COLUMN_W = 52
SPOT_SIZE = 20


@dataclass(frozen=True)
class BetSpot:
    """A clickable place on the felt."""

    key: str
    rect: pygame.Rect
    make: Callable[[int], rules.Bet]
    #: Smaller numbers are tested first, so a corner beats the cell under it.
    priority: int
    marker: Tuple[int, int]


def _cell_rect(number: int) -> pygame.Rect:
    column = (number - 1) // 3
    row = 2 - (number - 1) % 3
    return pygame.Rect(GRID_X + column * CELL_W, GRID_Y + row * CELL_H, CELL_W, CELL_H)


class RouletteScene(GameScene):
    title = "Roulette"
    subtitle = "Single zero  -  the house keeps 2.7%"
    game_key = "roulette"
    default_bet = 25

    def __init__(self, app) -> None:
        super().__init__(app)
        self.game = rules.RouletteGame(self.rng)
        self.spots: List[BetSpot] = []
        self.bets: Dict[str, int] = {}
        self._order: List[str] = []
        self.chip_value = 25
        self.result: Optional[rules.SpinResult] = None
        self.winning_number: Optional[int] = None

        self.spinning = False
        self._wheel_angle = 0.0
        self._ball_angle = 0.0
        self._ball_radius = float(WHEEL_RADIUS - 12)
        self._wheel_tween: Optional[anim.Tween] = None
        self._ball_tween: Optional[anim.Tween] = None
        self._radius_tween: Optional[anim.Tween] = None
        self._settle_timer = 0.0
        self._wheel_face: Optional[pygame.Surface] = None

        self._build_spots()
        self._build_widgets()

    # -------------------------------------------------------------- table --
    def _build_spots(self) -> None:
        spots: List[BetSpot] = []

        zero = pygame.Rect(GRID_X - ZERO_W, GRID_Y, ZERO_W, CELL_H * 3)
        spots.append(BetSpot("straight-0", zero,
                             lambda amount: rules.straight(0, amount), 40, zero.center))

        for number in range(1, 37):
            rect = _cell_rect(number)
            spots.append(BetSpot(f"straight-{number}", rect,
                                 lambda amount, n=number: rules.straight(n, amount),
                                 40, rect.center))

        # Splits between side-by-side numbers (n and n+3).
        for number in range(1, 34):
            left, right = _cell_rect(number), _cell_rect(number + 3)
            point = (left.right, left.centery)
            rect = pygame.Rect(0, 0, SPOT_SIZE, SPOT_SIZE)
            rect.center = point
            spots.append(BetSpot(f"split-{number}-{number + 3}", rect,
                                 lambda amount, a=number, b=number + 3: rules.split(a, b, amount),
                                 20, point))

        # Splits between numbers stacked in the same column.
        for number in range(1, 37):
            if (number - 1) % 3 == 2:
                continue
            lower, upper = _cell_rect(number), _cell_rect(number + 1)
            point = (lower.centerx, lower.top)
            rect = pygame.Rect(0, 0, SPOT_SIZE, SPOT_SIZE)
            rect.center = point
            spots.append(BetSpot(f"split-{number}-{number + 1}", rect,
                                 lambda amount, a=number, b=number + 1: rules.split(a, b, amount),
                                 20, point))

        # Corners sit on the crossings of four cells.
        for number in range(1, 34):
            if (number - 1) % 3 == 2:
                continue
            cell = _cell_rect(number)
            point = (cell.right, cell.top)
            rect = pygame.Rect(0, 0, SPOT_SIZE, SPOT_SIZE)
            rect.center = point
            spots.append(BetSpot(f"corner-{number}", rect,
                                 lambda amount, n=number: rules.corner(n, amount),
                                 10, point))

        # Streets and six lines hang off the bottom edge of the grid.
        bottom = GRID_Y + CELL_H * 3
        for column in range(12):
            start = column * 3 + 1
            point = (GRID_X + column * CELL_W + CELL_W // 2, bottom)
            rect = pygame.Rect(0, 0, CELL_W - SPOT_SIZE, SPOT_SIZE)
            rect.center = point
            spots.append(BetSpot(f"street-{start}", rect,
                                 lambda amount, s=start: rules.street(s, amount), 25, point))
        for column in range(11):
            start = column * 3 + 1
            point = (GRID_X + (column + 1) * CELL_W, bottom)
            rect = pygame.Rect(0, 0, SPOT_SIZE, SPOT_SIZE)
            rect.center = point
            spots.append(BetSpot(f"sixline-{start}", rect,
                                 lambda amount, s=start: rules.six_line(s, amount), 10, point))

        # Column bets down the right hand edge.
        for index in range(3):
            rect = pygame.Rect(GRID_X + CELL_W * 12, GRID_Y + (2 - index) * CELL_H,
                               COLUMN_W, CELL_H)
            spots.append(BetSpot(f"column-{index}", rect,
                                 lambda amount, i=index: rules.column(i, amount),
                                 40, rect.center))

        # Dozens then the even-money bets.
        dozen_y = bottom + 10
        for index in range(3):
            rect = pygame.Rect(GRID_X + index * CELL_W * 4, dozen_y, CELL_W * 4, 40)
            spots.append(BetSpot(f"dozen-{index}", rect,
                                 lambda amount, i=index: rules.dozen(i, amount),
                                 40, rect.center))

        outside_y = dozen_y + 46
        outside = [
            ("low", rules.low), ("even", rules.even), ("red", rules.red),
            ("black", rules.black), ("odd", rules.odd), ("high", rules.high),
        ]
        width = CELL_W * 12 // 6
        for index, (name, maker) in enumerate(outside):
            rect = pygame.Rect(GRID_X + index * width, outside_y, width, 40)
            spots.append(BetSpot(name, rect,
                                 lambda amount, m=maker: m(amount), 40, rect.center))

        spots.sort(key=lambda spot: spot.priority)
        self.spots = spots
        self._spot_by_key = {spot.key: spot for spot in spots}

    def _build_widgets(self) -> None:
        self.rail = ui.ChipRail((40, 566), config.CHIP_DENOMINATIONS,
                                self._pick_chip, radius=24)
        self.rail.affordable = lambda amount: self.bank.chips >= amount + self.total_staked
        self.add(self.rail)

        rects = ui.button_row(40, 626, 96, 40, 3, gap=10)
        self.add(ui.Button(rects[0], "Undo", self._undo, ui.GHOST, pygame.K_z, "Z",
                           font=self.fonts.tiny(bold=True), radius=6))
        self.add(ui.Button(rects[1], "Clear", self._clear, ui.GHOST, pygame.K_c, "C",
                           font=self.fonts.tiny(bold=True), radius=6))
        self.add(ui.Button(rects[2], "Rebet", self._rebet, ui.GHOST, pygame.K_r, "R",
                           font=self.fonts.tiny(bold=True), radius=6))

        self.spin_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH - 250, 610, 210, 56), "SPIN",
            self._spin, ui.PRIMARY, pygame.K_SPACE, "SPACE",
            font=self.fonts.large(bold=True),
        )
        self.add(self.spin_button)

    # --------------------------------------------------------------- bets --
    @property
    def total_staked(self) -> int:
        return sum(self.bets.values())

    def _pick_chip(self, value: int) -> None:
        self.chip_value = value

    def _place(self, spot: BetSpot) -> None:
        if self.spinning:
            return
        if self.bank.chips < self.total_staked + self.chip_value:
            self.toast("Not enough chips", theme.LOSE)
            self.audio.play("back")
            return
        self.bets[spot.key] = self.bets.get(spot.key, 0) + self.chip_value
        self._order.append(spot.key)
        self.audio.play("chip")

    def _undo(self) -> None:
        if self.spinning or not self._order:
            return
        key = self._order.pop()
        remaining = self.bets.get(key, 0) - self.chip_value
        if remaining > 0:
            self.bets[key] = remaining
        else:
            self.bets.pop(key, None)
        self.audio.play("back")

    def _clear(self) -> None:
        if self.spinning:
            return
        self.bets.clear()
        self._order.clear()
        self.audio.play("back")

    def _rebet(self) -> None:
        if self.spinning or not getattr(self, "_last_bets", None):
            return
        total = sum(self._last_bets.values())
        if self.bank.chips < total:
            self.toast("Not enough chips to repeat", theme.LOSE)
            return
        self.bets = dict(self._last_bets)
        self._order = list(self._last_order)
        self.audio.play("chip")

    # -------------------------------------------------------------- spin --
    def _spin(self) -> None:
        if self.spinning or not self.bets:
            if not self.bets:
                self.toast("Place a bet first", theme.TEXT_DIM)
            return
        total = self.total_staked
        if not self.wager(total):
            return

        self._last_bets = dict(self.bets)
        self._last_order = list(self._order)

        number = self.game.spin()
        self.winning_number = number
        bets = [self._spot_by_key[key].make(amount) for key, amount in self.bets.items()]
        self.result = self.game.settle(bets, number)

        duration = 3.4
        final_wheel = self._wheel_angle + math.tau * 3.0

        self._wheel_tween = anim.Tween(
            self._wheel_angle, final_wheel, duration, anim.ease_out_cubic,
        )
        # Finish the ball on the winning pocket as it will sit once the wheel
        # has stopped, then run it backwards a few turns for the spin.
        final_ball = rules.pocket_angle(number, final_wheel)
        self._ball_tween = anim.Tween(
            self._ball_angle, final_ball - math.tau * 7, duration,
            anim.ease_out_cubic,
        )
        self._radius_tween = anim.Tween(
            float(WHEEL_RADIUS - 12), float(WHEEL_RADIUS - 38), duration,
            anim.ease_in_out_quad,
        )
        self.spinning = True
        self._settle_timer = duration + 0.5
        self.audio.play("spin")
        self.last_result_text = ""

    def _finish_spin(self) -> None:
        self.spinning = False
        result = self.result
        if not result:
            return
        self.award(result.total_returned)
        self.settle(result.total_staked, result.total_returned,
                    celebrate_at=WHEEL_CENTRE)
        for bet in result.winners:
            if len(bet.numbers) == 1:
                self.bank.unlock("straight_up")
        self.bets.clear()
        self._order.clear()
        self.rng.next_round()

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        if super().handle_event(event):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            for spot in self.spots:
                if spot.rect.collidepoint(event.pos):
                    if event.button == 1:
                        self._place(spot)
                    else:
                        self._remove(spot)
                    return True
        return False

    def _remove(self, spot: BetSpot) -> None:
        if self.spinning or spot.key not in self.bets:
            return
        self.bets.pop(spot.key)
        self._order = [key for key in self._order if key != spot.key]
        self.audio.play("back")

    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._hover_spot = None
        if not self.spinning:
            for spot in self.spots:
                if spot.rect.collidepoint(mouse_pos):
                    self._hover_spot = spot
                    break

        if self.spinning:
            for tween, attribute in (
                (self._wheel_tween, "_wheel_angle"),
                (self._ball_tween, "_ball_angle"),
                (self._radius_tween, "_ball_radius"),
            ):
                if tween:
                    tween.update(dt)
                    setattr(self, attribute, tween.value)
            self._settle_timer -= dt
            if self._settle_timer <= 0:
                self._finish_spin()
        else:
            # The wheel idles between spins; a ball that has already settled
            # rides around in its pocket rather than drifting off the number.
            drift = dt * 0.12
            self._wheel_angle += drift
            self._ball_angle += drift

        self.spin_button.enabled = not self.spinning and bool(self.bets)
        self.rail.enabled = not self.spinning

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (16, 68, 50), theme.BG_DEEP)
        render.vignette(surface, 165)

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_wheel(surface)
        self._draw_layout(surface)
        self._draw_placed_chips(surface)
        self._draw_status(surface)
        self._draw_history(surface)

    # ------------------------------------------------------------- wheel --
    def _build_wheel_face(self) -> pygame.Surface:
        size = WHEEL_RADIUS * 2 + 8
        face = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)
        pygame.draw.circle(face, theme.WOOD, centre, WHEEL_RADIUS)
        pygame.draw.circle(face, theme.WOOD_LIGHT, centre, WHEEL_RADIUS, 4)

        pockets = len(rules.WHEEL_ORDER)
        step = math.tau / pockets
        font = theme.fonts().tiny(bold=True)
        for index, number in enumerate(rules.WHEEL_ORDER):
            start = index * step
            colour = {
                "green": (18, 122, 78), "red": theme.CARD_RED, "black": (26, 26, 30),
            }[rules.colour_of(number)]
            points = [centre]
            for step_index in range(7):
                angle = start + step * step_index / 6
                points.append((centre[0] + math.cos(angle) * (WHEEL_RADIUS - 6),
                               centre[1] + math.sin(angle) * (WHEEL_RADIUS - 6)))
            pygame.draw.polygon(face, colour, points)

            mid = start + step / 2
            label = font.render(str(number), True, theme.TEXT)
            label = pygame.transform.rotate(label, -math.degrees(mid) - 90)
            position = (centre[0] + math.cos(mid) * (WHEEL_RADIUS - 24),
                        centre[1] + math.sin(mid) * (WHEEL_RADIUS - 24))
            face.blit(label, label.get_rect(center=position))

        pygame.draw.circle(face, theme.GOLD_DIM, centre, WHEEL_RADIUS - 42, 3)
        pygame.draw.circle(face, theme.WOOD_LIGHT, centre, WHEEL_RADIUS - 46)
        for index in range(8):
            angle = index * math.tau / 8
            tip = (centre[0] + math.cos(angle) * (WHEEL_RADIUS - 48),
                   centre[1] + math.sin(angle) * (WHEEL_RADIUS - 48))
            pygame.draw.line(face, theme.darken(theme.WOOD, 0.25), centre, tip, 3)
        pygame.draw.circle(face, theme.GOLD, centre, 24)
        pygame.draw.circle(face, theme.GOLD_BRIGHT, centre, 24, 2)
        pygame.draw.circle(face, theme.WOOD, centre, 15)
        pygame.draw.circle(face, theme.GOLD_DIM, centre, 6)
        return face

    def _draw_wheel(self, surface: pygame.Surface) -> None:
        if self._wheel_face is None:
            self._wheel_face = self._build_wheel_face()
        rotated = pygame.transform.rotate(self._wheel_face,
                                          -math.degrees(self._wheel_angle))
        surface.blit(rotated, rotated.get_rect(center=WHEEL_CENTRE))

        ball = (WHEEL_CENTRE[0] + math.cos(self._ball_angle) * self._ball_radius,
                WHEEL_CENTRE[1] + math.sin(self._ball_angle) * self._ball_radius)
        render.circle(surface, ball, 7, theme.TEXT)
        render.circle(surface, ball, 7, theme.TEXT_MUTED, 1)

        if self.winning_number is not None and not self.spinning:
            colour = {
                "green": theme.WIN, "red": theme.CARD_RED, "black": theme.TEXT,
            }[rules.colour_of(self.winning_number)]
            badge = pygame.Rect(0, 0, 92, 48)
            badge.center = (WHEEL_CENTRE[0], WHEEL_CENTRE[1] + WHEEL_RADIUS + 28)
            render.panel(surface, badge, theme.PANEL, colour, radius=10)
            render.text(surface, self.fonts.large(bold=True), str(self.winning_number),
                        badge.center, colour, anchor="center")

    # ------------------------------------------------------------ layout --
    def _draw_layout(self, surface: pygame.Surface) -> None:
        zero = pygame.Rect(GRID_X - ZERO_W, GRID_Y, ZERO_W, CELL_H * 3)
        self._draw_cell(surface, zero, "0", (18, 122, 78), 0)

        for number in range(1, 37):
            colour = theme.CARD_RED if number in rules.RED_NUMBERS else (26, 26, 30)
            self._draw_cell(surface, _cell_rect(number), str(number), colour, number)

        for index in range(3):
            rect = pygame.Rect(GRID_X + CELL_W * 12, GRID_Y + (2 - index) * CELL_H,
                               COLUMN_W, CELL_H)
            self._draw_cell(surface, rect, "2:1", theme.FELT_DARK, None, small=True)

        bottom = GRID_Y + CELL_H * 3
        for index, label in enumerate(("1st 12", "2nd 12", "3rd 12")):
            rect = pygame.Rect(GRID_X + index * CELL_W * 4, bottom + 10, CELL_W * 4, 40)
            self._draw_cell(surface, rect, label, theme.FELT_DARK, None, small=True)

        outside_y = bottom + 56
        width = CELL_W * 12 // 6
        labels = [("1-18", theme.FELT_DARK), ("EVEN", theme.FELT_DARK),
                  ("RED", theme.CARD_RED), ("BLACK", (26, 26, 30)),
                  ("ODD", theme.FELT_DARK), ("19-36", theme.FELT_DARK)]
        for index, (label, colour) in enumerate(labels):
            rect = pygame.Rect(GRID_X + index * width, outside_y, width, 40)
            self._draw_cell(surface, rect, label, colour, None, small=True)

        if getattr(self, "_hover_spot", None) is not None:
            spot = self._hover_spot
            pygame.draw.rect(surface, theme.GOLD, spot.rect, 2, border_radius=4)

    def _draw_cell(self, surface: pygame.Surface, rect: pygame.Rect, label: str,
                   colour, number: Optional[int], small: bool = False) -> None:
        won = (
            number is not None
            and self.winning_number == number
            and not self.spinning
        )
        fill = theme.lighten(colour, 0.35) if won else colour
        pygame.draw.rect(surface, fill, rect)
        pygame.draw.rect(surface, theme.GOLD_DIM if won else theme.mix(theme.FELT, theme.TEXT, 0.25),
                         rect, 2 if won else 1)
        font = self.fonts.tiny(bold=True) if small else self.fonts.small(bold=True)
        render.text(surface, font, label, rect.center, theme.TEXT, anchor="center")

    def _draw_placed_chips(self, surface: pygame.Surface) -> None:
        for key, amount in self.bets.items():
            spot = self._spot_by_key[key]
            pieces = cardrender.chips_for_amount(amount, config.CHIP_DENOMINATIONS)
            denomination = pieces[0][0] if pieces else 1
            chip = cardrender.chip_surface(denomination, 15)
            surface.blit(chip, chip.get_rect(center=spot.marker))
            render.text(surface, self.fonts.tiny(bold=True), f"{amount:,}",
                        (spot.marker[0], spot.marker[1] + 18), theme.GOLD, anchor="center")

    # ------------------------------------------------------------ status --
    def _draw_status(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(40, 118, 344, 84)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.tiny(bold=True), "ON THE TABLE",
                    (box.x + 16, box.y + 12), theme.TEXT_DIM)
        render.text(surface, self.fonts.large(bold=True), f"{self.total_staked:,}",
                    (box.x + 16, box.y + 32), theme.GOLD)
        render.text(surface, self.fonts.tiny(), f"{len(self.bets)} bets placed",
                    (box.right - 16, box.y + 16), theme.TEXT_MUTED, anchor="topright")

        if getattr(self, "_hover_spot", None) is not None:
            bet = self._hover_spot.make(self.chip_value)
            render.text(surface, self.fonts.tiny(bold=True),
                        f"{bet.kind}  -  pays {bet.odds}:1",
                        (box.right - 16, box.y + 40), theme.GOLD, anchor="topright")

        if self.result and not self.spinning and self.last_result_text:
            draw_result_banner(surface, self.last_result_text, self.last_result_color,
                               (config.BASE_WIDTH // 2, 620), width=300)

        render.text(surface, self.fonts.tiny(),
                    "left click to add a chip  -  right click clears a spot",
                    (40, 548), theme.TEXT_MUTED)

    def _draw_history(self, surface: pygame.Surface) -> None:
        if not self.game.history:
            return
        box = pygame.Rect(40, 208, 344, 44)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=10)
        recent = list(reversed(self.game.history[-11:]))
        for index, number in enumerate(recent):
            colour = {
                "green": (18, 122, 78), "red": theme.CARD_RED, "black": (26, 26, 30),
            }[rules.colour_of(number)]
            chip = pygame.Rect(box.x + 10 + index * 30, box.y + 10, 24, 24)
            render.rounded_rect(surface, chip, colour, 12)
            render.text(surface, self.fonts.tiny(bold=True), str(number), chip.center,
                        theme.TEXT, anchor="center")
