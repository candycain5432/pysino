"""The books: lifetime numbers, a bankroll curve and the trophy cabinet."""

from __future__ import annotations

from typing import List, Tuple

import pygame

from .. import config
from ..core import render, theme, ui
from ..core.bank import ACHIEVEMENTS, GAMES
from ..core.scene import Scene

GAME_LABELS = {
    "blackjack": "Blackjack",
    "holdem": "Texas Hold'em",
    "slots": "Golden Reels",
    "mines": "Mines",
    "roulette": "Roulette",
    "videopoker": "Video Poker",
    "crash": "Crash",
}


class StatsScene(Scene):
    title = "Statistics"
    subtitle = "Everything the house remembers"

    def __init__(self, app) -> None:
        super().__init__(app)
        self.add(ui.Button(
            pygame.Rect(30, config.BASE_HEIGHT - 58, 140, 44),
            "Back", lambda: self.app.go_to("lobby"), ui.SECONDARY, pygame.K_b, "B",
        ))

    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (14, 34, 28), theme.BG_DEEP)
        render.vignette(surface, 160)

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_summary(surface)
        self._draw_curve(surface)
        self._draw_table(surface)
        self._draw_achievements(surface)

    # ------------------------------------------------------------ summary --
    def _draw_summary(self, surface: pygame.Surface) -> None:
        bank = self.bank
        cards: List[Tuple[str, str, tuple]] = [
            ("Chips", f"{bank.chips:,}", theme.GOLD),
            ("Peak stack", f"{bank.peak_chips:,}", theme.TEXT),
            ("Rounds", f"{bank.total_rounds:,}", theme.TEXT),
            ("Wagered", f"{bank.total_wagered:,}", theme.TEXT),
            ("Net", f"{bank.net:+,}",
             theme.WIN if bank.net > 0 else theme.LOSE if bank.net < 0 else theme.TEXT),
        ]
        width, gap = 220, 16
        total = len(cards) * width + (len(cards) - 1) * gap
        start = (config.BASE_WIDTH - total) // 2
        for index, (label, value, colour) in enumerate(cards):
            box = pygame.Rect(start + index * (width + gap), 78, width, 78)
            render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
            render.text(surface, self.fonts.tiny(bold=True), label.upper(),
                        (box.centerx, box.y + 14), theme.TEXT_MUTED, anchor="center")
            render.text(surface, self.fonts.large(bold=True), value,
                        (box.centerx, box.y + 46), colour, anchor="center")

    # -------------------------------------------------------------- curve --
    def _draw_curve(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(30, 174, 720, 210)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.small(bold=True), "BANKROLL",
                    (box.x + 16, box.y + 12), theme.GOLD)

        history = self.bank.balance_history
        plot = box.inflate(-48, -72)
        plot.y = box.y + 46
        if len(history) < 2:
            render.text(surface, self.fonts.tiny(), "play a few rounds to build a curve",
                        plot.center, theme.TEXT_MUTED, anchor="center")
            return

        low, high = min(history), max(history)
        span = max(1, high - low)
        points = []
        for index, value in enumerate(history):
            x = plot.x + plot.width * index / (len(history) - 1)
            y = plot.bottom - plot.height * (value - low) / span
            points.append((x, y))

        baseline = [(points[0][0], plot.bottom)] + points + [(points[-1][0], plot.bottom)]
        layer = pygame.Surface(config.BASE_SIZE, pygame.SRCALPHA)
        pygame.draw.polygon(layer, theme.with_alpha(theme.GOLD, 40), baseline)
        surface.blit(layer, (0, 0))
        pygame.draw.lines(surface, theme.GOLD, False, points, 2)

        render.text(surface, self.fonts.tiny(), f"{high:,}", (box.right - 16, plot.y - 4),
                    theme.TEXT_MUTED, anchor="topright")
        render.text(surface, self.fonts.tiny(), f"{low:,}",
                    (box.right - 16, plot.bottom - 12), theme.TEXT_MUTED, anchor="topright")

    # -------------------------------------------------------- per-game --
    def _draw_table(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(30, 396, 720, 252)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)

        headers = ("GAME", "ROUNDS", "WAGERED", "RETURN", "NET", "BEST")
        columns = (16, 210, 310, 430, 520, 630)
        for header, x in zip(headers, columns):
            anchor = "topleft" if x < 200 else "topright"
            position = (box.x + x, box.y + 14) if anchor == "topleft" else \
                (box.x + x + 70, box.y + 14)
            render.text(surface, self.fonts.tiny(bold=True), header, position,
                        theme.TEXT_MUTED, anchor=anchor)

        y = box.y + 40
        for key in GAMES:
            stats = self.bank.stats_for(key)
            row = pygame.Rect(box.x + 10, y, box.width - 20, 30)
            if stats.rounds:
                render.rounded_rect(surface, row, theme.darken(theme.PANEL_LIGHT, 0.3), 6)
            colour = theme.TEXT if stats.rounds else theme.TEXT_MUTED
            render.text(surface, self.fonts.small(bold=True), GAME_LABELS.get(key, key),
                        (box.x + 16, row.centery), colour, anchor="midleft")

            values = [
                (f"{stats.rounds:,}", columns[1], theme.TEXT_DIM),
                (f"{stats.wagered:,}", columns[2], theme.TEXT_DIM),
                (f"{stats.rtp * 100:.1f}%" if stats.wagered else "-", columns[3],
                 theme.TEXT_DIM),
                (f"{stats.net:+,}", columns[4],
                 theme.WIN if stats.net > 0 else theme.LOSE if stats.net < 0 else theme.TEXT_DIM),
                (f"{stats.biggest_win:,}" if stats.biggest_win else "-", columns[5],
                 theme.GOLD if stats.biggest_win else theme.TEXT_MUTED),
            ]
            for text, x, text_colour in values:
                render.text(surface, self.fonts.small(), text,
                            (box.x + x + 70, row.centery), text_colour, anchor="midright")
            y += 30

    # ------------------------------------------------------- achievements --
    def _draw_achievements(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(768, 174, config.BASE_WIDTH - 798, 474)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        unlocked = self.bank.achievements
        render.text(surface, self.fonts.small(bold=True),
                    f"ACHIEVEMENTS  {len(unlocked)}/{len(ACHIEVEMENTS)}",
                    (box.x + 16, box.y + 12), theme.GOLD)

        y = box.y + 36
        for achievement in ACHIEVEMENTS.values():
            has = achievement.key in unlocked
            row = pygame.Rect(box.x + 10, y, box.width - 20, 28)
            if has:
                render.rounded_rect(surface, row, theme.darken(theme.GOLD, 0.8), 6)
            icon_colour = theme.GOLD if has else theme.TEXT_MUTED
            render.text(surface, self.fonts.small(bold=True), achievement.icon,
                        (row.x + 10, row.centery), icon_colour, anchor="midleft")
            render.text(surface, self.fonts.tiny(bold=has), achievement.name,
                        (row.x + 32, row.centery - 6),
                        theme.TEXT if has else theme.TEXT_MUTED, anchor="midleft")
            render.text(surface, self.fonts.tiny(), achievement.description,
                        (row.x + 32, row.centery + 7),
                        theme.TEXT_DIM if has else theme.TEXT_MUTED, anchor="midleft")
            y += 27
