"""Mines: pick gems off a five by five grid and cash out before a bomb."""

from __future__ import annotations

import math
from typing import Dict

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..games import mines as rules
from .base import BetControls, GameScene, draw_result_banner

TILE = 84
GAP = 9
GRID_ORIGIN = (390, 132)


class MinesScene(GameScene):
    title = "Mines"
    subtitle = "Cash out whenever you like  -  one bomb ends it"
    game_key = "mines"
    default_bet = 50

    def __init__(self, app) -> None:
        super().__init__(app)
        self.game = rules.MinesGame(rng=self.rng)
        self.mine_count = int(self.bank.settings.get("mines_count", 3) or 3)
        self.staked = 0
        self._reveal_time: Dict[int, float] = {}
        self._shake = 0.0
        self._flash = 0.0
        self.bet_controls = BetControls(self, (40, 500))
        self._build_buttons()

    # ------------------------------------------------------------ widgets --
    def _build_buttons(self) -> None:
        self.mine_slider = ui.Slider(
            pygame.Rect(40, 430, 260, 34), rules.MIN_MINES, rules.MAX_MINES,
            self.mine_count, self._set_mines, step=1, label="Mines",
            formatter=lambda value: f"{int(value)}",
        )
        self.add(self.mine_slider)

        self.start_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 190, 612, 180, 52), "Place Bet",
            self._start, ui.PRIMARY, pygame.K_SPACE, "SPACE",
        )
        self.add(self.start_button)

        self.cash_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 + 10, 612, 180, 52), "Cash Out",
            self._cash_out, ui.SUCCESS, pygame.K_c, "C",
        )
        self.add(self.cash_button)

    def _set_mines(self, value: float) -> None:
        if self.game.state is rules.State.PLAYING:
            return
        self.mine_count = int(value)
        self.bank.settings["mines_count"] = self.mine_count

    # ------------------------------------------------------------ actions --
    def _start(self) -> None:
        if self.game.state is rules.State.PLAYING:
            return
        bet = self.clamp_bet(self.bet)
        if not self.wager(bet):
            return
        self.bet = bet
        self.staked = bet
        self._reveal_time.clear()
        self.last_result_text = ""
        self.game.start(bet, self.mine_count)
        self.audio.play("select")

    def _cash_out(self) -> None:
        if self.game.state is not rules.State.PLAYING or not self.game.revealed:
            return
        payout = self.game.cash_out()
        self._finish(payout)

    def _finish(self, payout: int) -> None:
        multiplier = self.game.multiplier
        self.award(payout)
        self.settle(self.staked, payout, celebrate_at=self._grid_rect().center)
        if payout > 0:
            self.audio.play("cash")
            if multiplier >= 10:
                self.bank.unlock("diamond_hands")
            if self.game.is_cleared:
                self.bank.unlock("clean_sweep")
            self.last_result_text = f"{multiplier:.2f}x  -  +{payout - self.staked:,}"
        self.rng.next_round()

    def _reveal(self, position: int) -> None:
        if self.game.state is not rules.State.PLAYING:
            return
        if position in self.game.revealed:
            return
        safe = self.game.reveal(position)
        self._reveal_time[position] = self.time
        if safe:
            self.audio.play("gem")
            centre = self._tile_rect(position).center
            self.particles.sparks(centre, 14, theme.GEM if hasattr(theme, "GEM") else theme.INFO)
            if self.game.state is rules.State.CASHED:
                self._finish(self.game.payout)
        else:
            self.audio.play("bomb")
            self._shake = 0.45
            self._flash = 0.6
            centre = self._tile_rect(position).center
            self.particles.smoke(centre, 22)
            self.particles.sparks(centre, 26, theme.LOSE)
            self.settle(self.staked, 0, celebrate_at=centre)
            self.last_result_text = "Boom"
            self.rng.next_round()

    # ------------------------------------------------------------- layout --
    def _grid_rect(self) -> pygame.Rect:
        span = rules.GRID_SIZE * TILE + (rules.GRID_SIZE - 1) * GAP
        return pygame.Rect(GRID_ORIGIN[0], GRID_ORIGIN[1], span, span)

    def _tile_rect(self, position: int) -> pygame.Rect:
        row, column = divmod(position, rules.GRID_SIZE)
        offset = (0, 0)
        if self._shake > 0:
            magnitude = self._shake * 12
            offset = (math.sin(self.time * 60) * magnitude,
                      math.cos(self.time * 53) * magnitude)
        return pygame.Rect(
            int(GRID_ORIGIN[0] + column * (TILE + GAP) + offset[0]),
            int(GRID_ORIGIN[1] + row * (TILE + GAP) + offset[1]),
            TILE, TILE,
        )

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        if super().handle_event(event):
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.game.state is rules.State.PLAYING:
                for position in range(rules.TILE_COUNT):
                    if self._tile_rect(position).collidepoint(event.pos):
                        self._reveal(position)
                        return True
        return False

    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._shake = max(0.0, self._shake - dt)
        self._flash = max(0.0, self._flash - dt * 1.6)
        playing = self.game.state is rules.State.PLAYING
        self.start_button.visible = not playing
        self.start_button.enabled = not playing and self.can_afford()
        self.cash_button.visible = playing
        self.cash_button.enabled = playing and bool(self.game.revealed)
        if playing:
            self.cash_button.label = f"Cash {self.game.payout:,}"
        self.mine_slider.enabled = not playing
        self.bet_controls.set_enabled(not playing)

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (20, 30, 56), theme.BG_DEEP)
        render.vignette(surface, 170)
        if self._flash > 0:
            veil = pygame.Surface(config.BASE_SIZE, pygame.SRCALPHA)
            veil.fill(theme.with_alpha(theme.LOSE, int(90 * self._flash)))
            surface.blit(veil, (0, 0))

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_grid(surface)
        self._draw_side_panel(surface)
        self._draw_ladder(surface)
        self.bet_controls.draw(surface)
        # The banner sits in the gap between the top bar and the grid, so it
        # stays single-line to avoid growing into either.
        if self.game.state is rules.State.BUSTED and self.last_result_text:
            draw_result_banner(surface, f"BOOM   -{self.staked:,}", theme.LOSE,
                               (self._grid_rect().centerx, 94), width=340)
        elif self.game.state is rules.State.CASHED and self.last_result_text:
            draw_result_banner(surface, self.last_result_text, theme.WIN,
                               (self._grid_rect().centerx, 94), width=420)

    def _draw_grid(self, surface: pygame.Surface) -> None:
        finished = self.game.state in (rules.State.BUSTED, rules.State.CASHED)
        for position in range(rules.TILE_COUNT):
            rect = self._tile_rect(position)
            revealed = position in self.game.revealed
            is_mine = position in self.game.mine_positions
            hit = position == self.game.hit_position

            if revealed:
                age = self.time - self._reveal_time.get(position, self.time)
                scale = anim.ease_out_back(min(1.0, age / 0.25))
                box = rect.inflate(int(-TILE * (1 - scale) * 0.5),
                                   int(-TILE * (1 - scale) * 0.5))
                render.rounded_rect(surface, box, theme.darken(theme.INFO, 0.55), 10)
                render.rounded_rect(surface, box, theme.INFO, 10, width=2)
                cardrender.draw_pip(surface, box.inflate(-30, -30), "d",
                                    theme.lighten(theme.INFO, 0.35))
            elif finished and is_mine:
                render.rounded_rect(surface, rect,
                                    theme.darken(theme.LOSE, 0.35 if hit else 0.65), 10)
                render.rounded_rect(surface, rect, theme.LOSE, 10, width=2 if hit else 1)
                self._draw_bomb(surface, rect, bright=hit)
            else:
                shade = theme.PANEL_LIGHT
                if self.game.state is rules.State.PLAYING:
                    shade = theme.mix(theme.PANEL_LIGHT, theme.PANEL,
                                      0.5 + 0.5 * math.sin(self.time * 2 + position))
                render.panel(surface, rect, shade, theme.PANEL_EDGE, radius=10, shadow=False)
                render.text(surface, self.fonts.tiny(), "?", rect.center,
                            theme.TEXT_MUTED, anchor="center")

    def _draw_bomb(self, surface: pygame.Surface, rect: pygame.Rect, bright: bool) -> None:
        centre = rect.center
        radius = rect.width // 4
        body = theme.LOSE if bright else theme.darken(theme.LOSE, 0.35)
        render.circle(surface, centre, radius, body)
        render.circle(surface, (centre[0] - radius // 3, centre[1] - radius // 3),
                      max(2, radius // 4), theme.lighten(body, 0.5))
        pygame.draw.line(surface, theme.WARN,
                         (centre[0] + radius // 2, centre[1] - radius // 2),
                         (centre[0] + radius, centre[1] - radius), 3)

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(40, 118, 260, 290)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)

        render.text(surface, self.fonts.tiny(bold=True), "MULTIPLIER",
                    (box.x + 16, box.y + 14), theme.TEXT_DIM)
        multiplier = self.game.multiplier if self.game.picks else 1.0
        colour = theme.GOLD if self.game.picks else theme.TEXT_MUTED
        render.text(surface, self.fonts.title(bold=True), f"{multiplier:.2f}x",
                    (box.x + 16, box.y + 34), colour)

        render.text(surface, self.fonts.tiny(bold=True), "CASH OUT VALUE",
                    (box.x + 16, box.y + 96), theme.TEXT_DIM)
        value = self.game.payout if self.game.state is rules.State.PLAYING else 0
        render.text(surface, self.fonts.large(bold=True), f"{value:,}",
                    (box.x + 16, box.y + 116), theme.WIN if value else theme.TEXT_MUTED)

        nxt = self.game.next_multiplier
        if nxt and self.game.state is rules.State.PLAYING:
            render.text(surface, self.fonts.tiny(),
                        f"next pick pays {nxt:.2f}x  ({int(self.staked * nxt):,})",
                        (box.x + 16, box.y + 158), theme.TEXT_DIM)

        rows = [
            ("Mines", str(self.mine_count)),
            ("Gems found", f"{self.game.picks} / {rules.TILE_COUNT - self.mine_count}"),
            ("Stake", f"{self.staked:,}"),
        ]
        for index, (label, text) in enumerate(rows):
            row = pygame.Rect(box.x + 16, box.y + 192 + index * 26, box.width - 32, 22)
            render.text(surface, self.fonts.small(), label, (row.x, row.centery),
                        theme.TEXT_DIM, anchor="midleft")
            render.text(surface, self.fonts.small(bold=True), text,
                        (row.right, row.centery), theme.TEXT, anchor="midright")

    def _draw_ladder(self, surface: pygame.Surface) -> None:
        """The next few multipliers, so the risk is always visible."""
        box = pygame.Rect(968, 150, 272, 300)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.small(bold=True), "PAYOUT LADDER",
                    (box.centerx, box.y + 14), theme.GOLD, anchor="center")
        render.text(surface, self.fonts.tiny(), f"{self.mine_count} mines",
                    (box.centerx, box.y + 34), theme.TEXT_MUTED, anchor="center")

        safe = rules.TILE_COUNT - self.mine_count
        start = max(0, self.game.picks - 2)
        shown = list(range(start + 1, min(safe, start + 10) + 1))
        for index, picks in enumerate(shown):
            row = pygame.Rect(box.x + 12, box.y + 56 + index * 24, box.width - 24, 22)
            current = picks == self.game.picks
            if current:
                render.rounded_rect(surface, row, theme.darken(theme.GOLD, 0.7), 6)
            colour = theme.GOLD if current else theme.TEXT_DIM
            label = f"{picks} gem" if picks == 1 else f"{picks} gems"
            render.text(surface, self.fonts.tiny(bold=current), label,
                        (row.x + 8, row.centery), colour, anchor="midleft")
            value = rules.multiplier_for(self.mine_count, picks)
            render.text(surface, self.fonts.tiny(bold=current), f"{value:.2f}x",
                        (row.right - 8, row.centery), colour, anchor="midright")
