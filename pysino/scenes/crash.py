"""Crash: a multiplier curve that dies without warning."""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

from .. import config
from ..core import anim, render, theme, ui
from ..games import crash as rules
from .base import BetControls, GameScene, draw_result_banner

GRAPH = pygame.Rect(330, 120, 610, 380)
#: Seconds of curve kept on screen before the view starts scrolling.
WINDOW_SECONDS = 6.0


class CrashScene(GameScene):
    title = "Crash"
    subtitle = "Cash out before the curve gives up"
    game_key = "crash"
    default_bet = 50

    def __init__(self, app) -> None:
        super().__init__(app)
        self.game = rules.CrashGame(rng=self.rng)
        self.history: List[float] = []
        self.staked = 0
        self.auto_target = float(self.bank.settings.get("crash_auto", 2.0) or 2.0)
        self.auto_enabled = bool(self.bank.settings.get("crash_auto_on", False))
        self._trail: List[Tuple[float, float]] = []
        self._result_timer = 0.0
        self._shake = 0.0
        self.bet_controls = BetControls(self, (40, 500))
        self._build_buttons()

    # ------------------------------------------------------------ widgets --
    def _build_buttons(self) -> None:
        self.launch_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 110, 600, 220, 58), "Place Bet",
            self._launch, ui.PRIMARY, pygame.K_SPACE, "SPACE",
            font=self.fonts.large(bold=True),
        )
        self.add(self.launch_button)

        self.auto_toggle = ui.ToggleButton(
            pygame.Rect(40, 430, 130, 34), "Auto", None, ui.GHOST,
            font=self.fonts.tiny(bold=True), radius=6,
            value=self.auto_enabled, on_change=self._toggle_auto,
        )
        self.add(self.auto_toggle)

        self.auto_slider = ui.Slider(
            pygame.Rect(180, 430, 120, 34), 1.1, 20.0, self.auto_target,
            self._set_auto, step=0.1, formatter=lambda v: f"{v:.1f}x",
        )
        self.add(self.auto_slider)

    def _toggle_auto(self, value: bool) -> None:
        self.auto_enabled = value
        self.bank.settings["crash_auto_on"] = value

    def _set_auto(self, value: float) -> None:
        self.auto_target = round(value, 2)
        self.bank.settings["crash_auto"] = self.auto_target

    # ------------------------------------------------------------ actions --
    def _launch(self) -> None:
        if self.game.state is rules.State.RUNNING:
            return
        bet = self.clamp_bet(self.bet)
        if not self.wager(bet):
            return
        self.bet = bet
        self.staked = bet
        self._trail = [(0.0, 1.0)]
        self.last_result_text = ""
        self.game.start(bet, self.auto_target if self.auto_enabled else None)
        self.audio.play("launch")

    def _cash_out(self) -> None:
        if self.game.state is not rules.State.RUNNING:
            return
        payout = self.game.cash_out()
        self._settle(payout)

    def _settle(self, payout: int) -> None:
        multiplier = self.game.cashed_at or self.game.crash_point
        self.award(payout)
        self.settle(self.staked, payout, celebrate_at=GRAPH.center)
        if payout:
            self.audio.play("cash")
            self.last_result_text = f"{multiplier:.2f}x"
            if multiplier >= 25:
                self.bank.unlock("moon")
        self.history.insert(0, self.game.crash_point)
        del self.history[12:]
        self._result_timer = 2.0
        self.rng.next_round()

    def _crashed(self) -> None:
        self.audio.play("crash")
        self._shake = 0.4
        self.particles.smoke(
            (GRAPH.x + self._curve_point(self.game.elapsed, self.game.crash_point)[0],
             self._curve_point(self.game.elapsed, self.game.crash_point)[1]), 20)
        self.settle(self.staked, 0, celebrate_at=GRAPH.center)
        self.last_result_text = f"Crashed at {self.game.crash_point:.2f}x"
        self.history.insert(0, self.game.crash_point)
        del self.history[12:]
        self._result_timer = 2.0
        self.rng.next_round()

    # ------------------------------------------------------------- events --
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            if self.game.state is rules.State.RUNNING:
                self._cash_out()
                return True
        return super().handle_event(event)

    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._shake = max(0.0, self._shake - dt)
        self._result_timer = max(0.0, self._result_timer - dt)

        if self.game.state is rules.State.RUNNING:
            was_running = True
            self.game.tick(dt)
            self._trail.append((self.game.elapsed, self.game.multiplier))
            if len(self._trail) > 900:
                del self._trail[:300]
            if self.game.state is rules.State.CASHED:
                self._settle(self.game.payout)
            elif self.game.state is rules.State.CRASHED:
                self._crashed()

        running = self.game.state is rules.State.RUNNING
        self.launch_button.label = (
            f"Cash Out {int(self.staked * self.game.multiplier):,}" if running else "Place Bet"
        )
        self.launch_button.style = ui.SUCCESS if running else ui.PRIMARY
        self.launch_button.on_click = self._cash_out if running else self._launch
        self.launch_button.enabled = running or self.can_afford()
        self.bet_controls.set_enabled(not running)
        self.auto_slider.enabled = not running
        self.auto_toggle.enabled = not running

    # ------------------------------------------------------------ drawing --
    def _curve_point(self, elapsed: float, multiplier: float) -> Tuple[int, int]:
        span = max(WINDOW_SECONDS, self.game.elapsed * 1.05)
        top = max(2.0, self.game.multiplier * 1.2)
        x = GRAPH.x + (elapsed / span) * GRAPH.width
        y = GRAPH.bottom - ((multiplier - 1.0) / (top - 1.0)) * GRAPH.height
        return (int(x), int(max(GRAPH.y, min(GRAPH.bottom, y))))

    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (16, 22, 48), theme.BG_DEEP)
        render.vignette(surface, 170)

    def draw_content(self, surface: pygame.Surface) -> None:
        offset = (0, 0)
        if self._shake > 0:
            offset = (math.sin(self.time * 70) * self._shake * 10,
                      math.cos(self.time * 61) * self._shake * 10)
        self._draw_graph(surface, offset)
        self._draw_side_panel(surface)
        self._draw_history(surface)
        self.bet_controls.draw(surface)

    def _draw_graph(self, surface: pygame.Surface, offset) -> None:
        frame = GRAPH.inflate(20, 20).move(offset)
        render.panel(surface, frame, theme.BG_RAISED, theme.PANEL_EDGE, radius=14)

        for index in range(1, 5):
            y = GRAPH.y + index * GRAPH.height // 5 + offset[1]
            pygame.draw.line(surface, theme.darken(theme.PANEL_EDGE, 0.4),
                             (GRAPH.x + offset[0], y), (GRAPH.right + offset[0], y), 1)

        if len(self._trail) > 1:
            points = [
                (point[0] + offset[0], point[1] + offset[1])
                for point in (self._curve_point(t, m) for t, m in self._trail)
            ]
            crashed = self.game.state is rules.State.CRASHED
            colour = theme.LOSE if crashed else theme.WIN
            pygame.draw.lines(surface, colour, False, points, 3)
            fill = [(points[0][0], GRAPH.bottom + offset[1])] + points + \
                   [(points[-1][0], GRAPH.bottom + offset[1])]
            if len(fill) > 2:
                layer = pygame.Surface(config.BASE_SIZE, pygame.SRCALPHA)
                pygame.draw.polygon(layer, theme.with_alpha(colour, 46), fill)
                surface.blit(layer, (0, 0))
            head = points[-1]
            if not crashed:
                render.circle(surface, head, 7, theme.GOLD_BRIGHT)
                render.circle(surface, head, 12, theme.with_alpha(theme.GOLD, 90))

        multiplier = self.game.multiplier
        colour = theme.TEXT
        if self.game.state is rules.State.RUNNING:
            colour = theme.WIN
        elif self.game.state is rules.State.CRASHED:
            colour = theme.LOSE
        elif self.game.state is rules.State.CASHED:
            colour = theme.GOLD
        label = f"{multiplier:.2f}x"
        render.text(surface, self.fonts.huge(bold=True), label,
                    (GRAPH.centerx + offset[0], GRAPH.centery + offset[1]),
                    colour, anchor="center", shadow=True)

        if self.game.state is rules.State.IDLE:
            render.text(surface, self.fonts.small(), "press SPACE to launch",
                        (GRAPH.centerx, GRAPH.centery + 54), theme.TEXT_DIM, anchor="center")
        elif self.game.state is rules.State.CRASHED and self._result_timer > 0:
            render.text(surface, self.fonts.body(bold=True), "CRASHED",
                        (GRAPH.centerx, GRAPH.centery + 54), theme.LOSE, anchor="center")
        elif self.game.state is rules.State.CASHED and self._result_timer > 0:
            won = self.game.payout - self.staked
            render.text(surface, self.fonts.body(bold=True), f"cashed out  +{won:,}",
                        (GRAPH.centerx, GRAPH.centery + 54), theme.WIN, anchor="center")

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(40, 118, 260, 290)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.tiny(bold=True), "STAKE",
                    (box.x + 16, box.y + 14), theme.TEXT_DIM)
        render.text(surface, self.fonts.large(bold=True), f"{self.staked:,}",
                    (box.x + 16, box.y + 34), theme.TEXT)

        render.text(surface, self.fonts.tiny(bold=True), "CASH OUT NOW",
                    (box.x + 16, box.y + 84), theme.TEXT_DIM)
        live = self.game.state is rules.State.RUNNING
        value = int(self.staked * self.game.multiplier) if live else 0
        render.text(surface, self.fonts.title(bold=True), f"{value:,}",
                    (box.x + 16, box.y + 104), theme.WIN if live else theme.TEXT_MUTED)

        render.text(surface, self.fonts.tiny(),
                    "Auto cash out fires the moment the curve reaches your target.",
                    (box.x + 16, box.y + 168), theme.TEXT_MUTED)
        stats = self.bank.stats_for(self.game_key)
        render.text(surface, self.fonts.tiny(), f"rounds {stats.rounds:,}",
                    (box.x + 16, box.bottom - 44), theme.TEXT_MUTED)
        render.text(surface, self.fonts.tiny(), f"best {stats.biggest_win:+,}",
                    (box.x + 16, box.bottom - 26), theme.TEXT_MUTED)

    def _draw_history(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(968, 118, 272, 290)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.small(bold=True), "RECENT CRASHES",
                    (box.centerx, box.y + 14), theme.GOLD, anchor="center")
        if not self.history:
            render.text(surface, self.fonts.tiny(), "no rounds yet",
                        (box.centerx, box.y + 48), theme.TEXT_MUTED, anchor="center")
            return
        for index, value in enumerate(self.history[:10]):
            row = pygame.Rect(box.x + 14, box.y + 44 + index * 24, box.width - 28, 22)
            colour = theme.LOSE if value < 2 else theme.WIN if value >= 10 else theme.GOLD
            render.rounded_rect(surface, row, theme.darken(colour, 0.78), 6)
            render.text(surface, self.fonts.tiny(bold=True), f"{value:.2f}x",
                        (row.x + 10, row.centery), colour, anchor="midleft")
