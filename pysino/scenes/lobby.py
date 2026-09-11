"""The lobby: pick a table, claim the daily bonus, check the books."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame

from .. import config
from ..core import cardrender, render, theme, ui
from ..core.cards import Card
from ..core.scene import Scene


@dataclass(frozen=True)
class GameEntry:
    key: str
    title: str
    tagline: str
    house: str
    accent: Tuple[int, int, int]
    icon: str


GAMES: Tuple[GameEntry, ...] = (
    GameEntry("blackjack", "Blackjack", "Six decks, dealer stands on soft 17",
              "House edge 0.5%", theme.WIN, "blackjack"),
    GameEntry("holdem", "Texas Hold'em", "No-limit cash game against three bots",
              "Skill vs bots", theme.INFO, "holdem"),
    GameEntry("slots", "Golden Reels", "20 lines, wilds, scatters, free spins",
              "RTP 95%", theme.GOLD, "slots"),
    GameEntry("roulette", "Roulette", "Single zero European wheel",
              "House edge 2.7%", theme.LOSE, "roulette"),
    GameEntry("mines", "Mines", "Find the gems, dodge the bombs",
              "House edge 1%", theme.PURPLE, "mines"),
    GameEntry("videopoker", "Video Poker", "Jacks or Better, full pay 9/6",
              "RTP 99.5%", theme.SILVER, "videopoker"),
    GameEntry("crash", "Crash", "Cash out before the curve dies",
              "House edge 1%", theme.WARN, "crash"),
)

CARD_SIZE = (272, 186)


class LobbyScene(Scene):
    title = "Lobby"
    escape_returns = False
    show_hud = True

    def __init__(self, app) -> None:
        super().__init__(app)
        self.subtitle = "Pick your poison"
        self._hover: Optional[int] = None
        self._rects: List[pygame.Rect] = []
        self._lift = [0.0] * len(GAMES)
        self._build_layout()
        self._build_buttons()

    # ------------------------------------------------------------- layout --
    def _build_layout(self) -> None:
        width, height = CARD_SIZE
        gap = 24
        self._rects = []
        rows = (GAMES[:4], GAMES[4:])
        top = 168
        for row_index, row in enumerate(rows):
            total = len(row) * width + (len(row) - 1) * gap
            start = (config.BASE_WIDTH - total) // 2
            y = top + row_index * (height + gap)
            for column in range(len(row)):
                self._rects.append(
                    pygame.Rect(start + column * (width + gap), y, width, height)
                )

    def _build_buttons(self) -> None:
        y = config.BASE_HEIGHT - 62
        rects = ui.centred_row(config.BASE_WIDTH // 2, y, 190, 44, 4, gap=14)
        self.bonus_button = ui.Button(
            rects[0], "Daily Bonus", self._claim_bonus, ui.PRIMARY,
            pygame.K_b, "B",
        )
        self.add(self.bonus_button)
        self.add(ui.Button(rects[1], "Statistics", lambda: self.app.go_to("stats"),
                           ui.SECONDARY, pygame.K_s, "S"))
        self.add(ui.Button(rects[2], "Settings", lambda: self.app.go_to("settings"),
                           ui.SECONDARY, pygame.K_o, "O"))
        self.add(ui.Button(rects[3], "Quit", self.app.quit, ui.GHOST, pygame.K_q, "Q"))

    # ------------------------------------------------------------ actions --
    def _claim_bonus(self) -> None:
        amount = self.bank.claim_daily_bonus()
        if amount:
            self.audio.play("cash")
            self.toast(f"Daily bonus: +{amount:,} chips", theme.GOLD)
            self.particles.coins((config.BASE_WIDTH // 2, config.BASE_HEIGHT - 80), 34)
        else:
            self.audio.play("back")
            self.toast("Already claimed today - come back tomorrow", theme.TEXT_DIM)

    def _open(self, index: int) -> None:
        entry = GAMES[index]
        self.audio.play("select")
        self.app.go_to(entry.key)

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        if super().handle_event(event):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self._rects):
                if rect.collidepoint(event.pos):
                    self._open(index)
                    return True
        if event.type == pygame.KEYDOWN and pygame.K_1 <= event.key <= pygame.K_7:
            index = event.key - pygame.K_1
            if index < len(GAMES):
                self._open(index)
                return True
        return False

    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._hover = None
        for index, rect in enumerate(self._rects):
            hovered = rect.collidepoint(mouse_pos)
            if hovered:
                self._hover = index
            target = 1.0 if hovered else 0.0
            self._lift[index] += (target - self._lift[index]) * min(1.0, dt * 12)
        self.bonus_button.enabled = self.bank.bonus_available
        self.bonus_button.label = "Daily Bonus" if self.bank.bonus_available else "Claimed"

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (14, 40, 32), theme.BG_DEEP)
        self._draw_backdrop_suits(surface)
        render.vignette(surface, 170)

    def _draw_backdrop_suits(self, surface: pygame.Surface) -> None:
        """Slow drifting suit marks, so the lobby is never completely still."""
        for index, suit in enumerate("shdc" * 2):
            phase = self.time * 0.22 + index * 1.7
            x = 90 + (index * 163) % (config.BASE_WIDTH - 60)
            y = 120 + math.sin(phase) * 26 + (index % 3) * 190
            size = 60 + (index % 3) * 22
            pip = cardrender.pip_surface(suit, size, theme.FELT_LIGHT)
            faded = pip.copy()
            faded.set_alpha(26)
            surface.blit(faded, (x, y))

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_masthead(surface)
        for index, entry in enumerate(GAMES):
            self._draw_game_card(surface, index, entry)
        self._draw_footer(surface)

    def _draw_masthead(self, surface: pygame.Surface) -> None:
        centre = config.BASE_WIDTH // 2
        render.text(surface, self.fonts.huge(bold=True), "PYSINO", (centre, 98),
                    theme.GOLD, anchor="center", shadow=True)
        render.text(surface, self.fonts.small(), "chips carry across every table",
                    (centre, 136), theme.TEXT_DIM, anchor="center")

    def _draw_game_card(self, surface: pygame.Surface, index: int, entry: GameEntry) -> None:
        lift = self._lift[index]
        rect = self._rects[index].move(0, int(-6 * lift))
        if lift > 0.01:
            render.glow(surface, rect, entry.accent, radius=14, spread=16,
                        alpha=int(90 * lift))
        render.panel(surface, rect, theme.mix(theme.PANEL, theme.PANEL_LIGHT, lift),
                     theme.mix(theme.PANEL_EDGE, entry.accent, lift), radius=14)

        art = pygame.Rect(rect.x, rect.y + 6, rect.width, 84)
        _draw_icon(surface, entry.icon, art, entry.accent, self.time + index)

        render.text(surface, self.fonts.body(bold=True), entry.title,
                    (rect.centerx, rect.y + 108), theme.TEXT, anchor="center")
        render.text(surface, self.fonts.tiny(), entry.tagline,
                    (rect.centerx, rect.y + 132), theme.TEXT_DIM, anchor="center")

        badge_font = self.fonts.tiny(bold=True)
        badge_width = badge_font.size(entry.house)[0] + 18
        badge = pygame.Rect(0, 0, badge_width, 20)
        badge.center = (rect.centerx, rect.bottom - 22)
        render.rounded_rect(surface, badge, theme.darken(entry.accent, 0.65), 10)
        render.text(surface, badge_font, entry.house, badge.center,
                    theme.lighten(entry.accent, 0.4), anchor="center")

        render.text(surface, self.fonts.tiny(bold=True), str(index + 1),
                    (rect.x + 12, rect.y + 10), theme.TEXT_MUTED)

    def _draw_footer(self, surface: pygame.Surface) -> None:
        stats = self.bank
        y = config.BASE_HEIGHT - 96
        pieces = [
            ("Rounds played", f"{stats.total_rounds:,}"),
            ("Lifetime wagered", f"{stats.total_wagered:,}"),
            ("Net", f"{stats.net:+,}"),
            ("Peak stack", f"{stats.peak_chips:,}"),
        ]
        total_width = 1040
        start = (config.BASE_WIDTH - total_width) // 2
        step = total_width // len(pieces)
        for index, (label, value) in enumerate(pieces):
            centre = start + step * index + step // 2
            colour = theme.TEXT
            if label == "Net":
                colour = theme.WIN if stats.net > 0 else theme.LOSE if stats.net < 0 else theme.TEXT
            render.text(surface, self.fonts.small(bold=True), value, (centre, y),
                        colour, anchor="center")
            render.text(surface, self.fonts.tiny(), label, (centre, y + 20),
                        theme.TEXT_MUTED, anchor="center")


# ------------------------------------------------------------- card icons --
def _draw_icon(surface: pygame.Surface, kind: str, rect: pygame.Rect,
               accent, time: float) -> None:
    painter = _ICONS.get(kind)
    if painter:
        painter(surface, rect, accent, time)


def _icon_blackjack(surface, rect, accent, time) -> None:
    size = (54, 76)
    lean = math.sin(time * 0.8) * 3
    for index, card in enumerate((Card(14, "s"), Card(13, "h"))):
        sprite = cardrender.card_surface(card, size)
        sprite = pygame.transform.rotate(sprite, (-12 + index * 20) + lean)
        surface.blit(sprite, sprite.get_rect(
            center=(rect.centerx - 22 + index * 44, rect.centery)))


def _icon_holdem(surface, rect, accent, time) -> None:
    for index in range(5):
        sprite = cardrender.card_surface(Card(10 + index, "shdcs"[index]), (34, 48))
        surface.blit(sprite, sprite.get_rect(
            center=(rect.centerx - 74 + index * 37, rect.centery)))


def _icon_slots(surface, rect, accent, time) -> None:
    from ..games import slots as slot_rules

    window = pygame.Rect(0, 0, 160, 64)
    window.center = rect.center
    render.rounded_rect(surface, window, theme.BG_DEEP, 8)
    render.rounded_rect(surface, window, theme.GOLD_DIM, 8, width=1)
    symbols = (slot_rules.SEVEN, slot_rules.SEVEN, slot_rules.SEVEN)
    font = theme.fonts().large(bold=True)
    for index, symbol in enumerate(symbols):
        wobble = math.sin(time * 2 + index) * 2
        render.text(surface, font, slot_rules.SYMBOL_GLYPHS[symbol],
                    (window.x + 32 + index * 48, window.centery + wobble),
                    theme.GOLD, anchor="center")


def _icon_roulette(surface, rect, accent, time) -> None:
    centre = rect.center
    radius = 38
    render.circle(surface, centre, radius, theme.WOOD)
    render.circle(surface, centre, radius - 5, theme.FELT_DARK)
    for index in range(18):
        angle = time * 0.6 + index * math.tau / 18
        colour = theme.LOSE if index % 2 else theme.INK
        point = (centre[0] + math.cos(angle) * (radius - 14),
                 centre[1] + math.sin(angle) * (radius - 14))
        render.circle(surface, point, 5, colour)
    render.circle(surface, centre, 10, theme.GOLD)
    ball_angle = -time * 2.2
    render.circle(surface, (centre[0] + math.cos(ball_angle) * (radius - 5),
                            centre[1] + math.sin(ball_angle) * (radius - 5)), 4, theme.TEXT)


def _icon_mines(surface, rect, accent, time) -> None:
    cell = 22
    start_x = rect.centerx - cell * 2 - 6
    start_y = rect.centery - cell - 6
    for row in range(3):
        for column in range(5):
            tile = pygame.Rect(start_x + column * (cell + 3), start_y + row * (cell + 3),
                               cell, cell)
            revealed = (row + column) % 4 == 0
            render.rounded_rect(surface, tile,
                                theme.PANEL_LIGHT if not revealed else theme.darken(accent, 0.5), 4)
            if revealed:
                cardrender.draw_pip(surface, tile.inflate(-8, -8), "d", accent)


def _icon_videopoker(surface, rect, accent, time) -> None:
    for index, card in enumerate((Card(14, "s"), Card(13, "s"), Card(12, "s"),
                                  Card(11, "s"), Card(10, "s"))):
        sprite = cardrender.card_surface(card, (36, 50))
        lift = -5 if index in (0, 2, 4) else 0
        surface.blit(sprite, sprite.get_rect(
            center=(rect.centerx - 78 + index * 39, rect.centery + lift)))


def _icon_crash(surface, rect, accent, time) -> None:
    points = []
    for step in range(34):
        fraction = step / 33
        x = rect.x + 60 + fraction * (rect.width - 130)
        y = rect.bottom - 12 - (fraction ** 2.3) * 62
        points.append((x, y))
    if len(points) > 1:
        pygame.draw.lines(surface, accent, False, points, 3)
    head = points[-1]
    render.circle(surface, head, 6, theme.GOLD_BRIGHT)
    render.text(surface, theme.fonts().small(bold=True), "x", (head[0] + 14, head[1] - 6),
                accent, anchor="midleft")


_ICONS: dict[str, Callable] = {
    "blackjack": _icon_blackjack,
    "holdem": _icon_holdem,
    "slots": _icon_slots,
    "roulette": _icon_roulette,
    "mines": _icon_mines,
    "videopoker": _icon_videopoker,
    "crash": _icon_crash,
}
