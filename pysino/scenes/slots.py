"""Golden Reels: a five reel, twenty line video slot."""

from __future__ import annotations

import random
from typing import List, Optional, Sequence, Tuple

import pygame

from .. import config
from ..core import anim, render, slotart, theme, ui
from ..games import slots as rules
from .base import BetControls, GameScene

WINDOW = pygame.Rect(330, 118, 620, 342)
CELL_WIDTH = WINDOW.width // rules.REELS
CELL_HEIGHT = WINDOW.height // rules.ROWS
#: Strip positions travelled per second while a reel is free-spinning.
SPIN_SPEED = 26.0


class Reel:
    """One spinning column.

    The reel scrolls a private copy of its strip.  When it is told where to
    stop, the three symbols it must show are written into the strip just ahead
    of the current position and the offset is eased onto them, which lands the
    reel exactly on the result without any visible snap.
    """

    def __init__(self, strip: Sequence[str]) -> None:
        self.strip: List[str] = list(strip)
        self.display: List[str] = list(strip)
        self.offset = float(random.randrange(len(strip)))
        self.spinning = False
        self.tween: Optional[anim.Tween] = None

    @property
    def settled(self) -> bool:
        return not self.spinning and self.tween is None

    def start(self) -> None:
        self.spinning = True
        self.tween = None

    def stop_on(self, symbols: Sequence[str], travel: int = 10,
               duration: float = 0.55, delay: float = 0.0) -> None:
        """Ease to a stop showing ``symbols`` top to bottom."""
        length = len(self.display)
        target = int(self.offset) + max(4, travel)
        for row, symbol in enumerate(symbols):
            self.display[(target + row) % length] = symbol
        self.spinning = False
        self._target = float(target)
        self.tween = anim.Tween(self.offset, self._target, duration,
                                anim.ease_out_cubic, delay)

    def update(self, dt: float) -> None:
        tween = self.tween
        if tween is not None:
            tween.update(dt)
            self.offset = tween.value
            if tween.done:
                self.offset = self._target
                self.tween = None
        elif self.spinning:
            self.offset += SPIN_SPEED * dt

    def symbol_at(self, row: int) -> str:
        return self.display[(int(self.offset) + row) % len(self.display)]

    @property
    def fraction(self) -> float:
        return self.offset - int(self.offset)


class SlotsScene(GameScene):
    title = "Golden Reels"
    subtitle = "20 lines  -  wilds  -  free spins"
    game_key = "slots"
    default_bet = 100
    min_bet = rules.LINE_COUNT

    def __init__(self, app) -> None:
        super().__init__(app)
        self.machine = rules.SlotMachine(self.rng)
        self.reels = [Reel(strip) for strip in rules.REEL_STRIPS]
        self.result: Optional[rules.SpinResult] = None
        self.win_ticker = ui.ValueTicker(0, rate=4.0)
        self.spinning = False
        self._settle_pending = False
        self._autospin_timer = 0.0
        self._highlight_cycle = 0.0
        self.bet_controls = BetControls(self, (40, 520))
        self._build_buttons()

    # ------------------------------------------------------------ widgets --
    def _build_buttons(self) -> None:
        self.spin_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 110, 600, 220, 58), "SPIN",
            self._spin, ui.PRIMARY, pygame.K_SPACE, "SPACE",
            font=self.fonts.large(bold=True),
        )
        self.add(self.spin_button)
        self.max_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 + 126, 610, 120, 40), "Max Bet",
            self._max_bet, ui.GHOST, pygame.K_m, "M", font=self.fonts.tiny(bold=True),
        )
        self.add(self.max_button)

    # -------------------------------------------------------------- rules --
    def clamp_bet(self, amount: int) -> int:
        """Stakes always divide evenly across the twenty paylines."""
        lines = rules.LINE_COUNT
        amount = super().clamp_bet(amount)
        snapped = (amount // lines) * lines
        return max(lines, min(snapped, (self.max_bet // lines) * lines))

    @property
    def line_bet(self) -> int:
        return max(1, self.bet // rules.LINE_COUNT)

    def _max_bet(self) -> None:
        self.bet = self.clamp_bet(self.max_bet)
        self.audio.play("chip")

    # ------------------------------------------------------------ spinning --
    def _spin(self) -> None:
        if self.spinning:
            return
        free = self.machine.in_free_spins
        total = self.clamp_bet(self.bet)
        if not free:
            if not self.bank.can_afford(total):
                self.toast("Not enough chips", theme.LOSE)
                return
            self.bet = total
            if not self.wager(total):
                return

        self.result = self.machine.spin(self.line_bet)
        self.spinning = True
        self._settle_pending = True
        self.win_ticker.set(0, immediate=True)
        self.audio.play("spin")

        for index, reel in enumerate(self.reels):
            reel.start()
            column = [self.result.grid[row][index] for row in range(rules.ROWS)]
            reel.stop_on(column, travel=12 + index * 3, duration=0.5,
                         delay=0.35 + index * 0.16)

    def _finish_spin(self) -> None:
        self._settle_pending = False
        result = self.result
        if result is None:
            return

        win = result.total_win
        self.win_ticker.set(win)
        if win:
            self.award(win)

        if result.was_free_spin:
            # Free spins are booked as pure winnings against a zero stake.
            self.settle(0, win, quiet=True)
            if win:
                self.audio.play("win")
                self.particles.coins(WINDOW.center, 24)
        else:
            self.settle(result.total_bet, win, celebrate_at=WINDOW.center)

        if result.free_spins_awarded:
            self.bank.unlock("free_spins")
            self.audio.play("jackpot")
            self.toast(f"{result.free_spins_awarded} free spins!", theme.GOLD, 3.0)
            self.particles.confetti(WINDOW.center, 80)
        for line_win in result.line_wins:
            if line_win.count == 5:
                self.bank.unlock("jackpot")
        self.rng.next_round()
        if self.machine.in_free_spins:
            self._autospin_timer = 1.4

    # -------------------------------------------------------------- frame --
    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._highlight_cycle += dt
        for reel in self.reels:
            reel.update(dt)

        if self.spinning and all(reel.settled for reel in self.reels):
            self.spinning = False
            self.audio.play("reel")
            if self._settle_pending:
                self._finish_spin()

        self.win_ticker.update(dt)

        if self._autospin_timer > 0:
            self._autospin_timer -= dt
            if self._autospin_timer <= 0 and not self.spinning:
                self._spin()

        idle = not self.spinning
        free = self.machine.in_free_spins
        self.spin_button.enabled = idle and (free or self.bank.can_afford(self.clamp_bet(self.bet)))
        self.spin_button.label = "FREE SPIN" if free else "SPIN"
        self.max_button.enabled = idle and not free
        self.bet_controls.set_enabled(idle and not free)

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (36, 22, 58), theme.BG_DEEP)
        render.vignette(surface, 170)

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_cabinet(surface)
        self._draw_reels(surface)
        self._draw_paytable(surface)
        self._draw_win_panel(surface)
        self.bet_controls.draw(surface)
        self._draw_free_spin_banner(surface)

    def _draw_cabinet(self, surface: pygame.Surface) -> None:
        frame = WINDOW.inflate(28, 28)
        render.glow(surface, frame, theme.GOLD, radius=16, spread=18, alpha=60)
        render.panel(surface, frame, theme.darken(theme.WOOD, 0.2), theme.GOLD, radius=16)
        render.rounded_rect(surface, WINDOW.inflate(8, 8), theme.BG_DEEP, 10)

    def _draw_reels(self, surface: pygame.Surface) -> None:
        clip = surface.get_clip()
        surface.set_clip(WINDOW)
        winning = self._winning_cells()
        for index, reel in enumerate(self.reels):
            column = pygame.Rect(WINDOW.x + index * CELL_WIDTH, WINDOW.y,
                                 CELL_WIDTH, WINDOW.height)
            shade = theme.BG_RAISED if index % 2 == 0 else theme.darken(theme.BG_RAISED, 0.18)
            pygame.draw.rect(surface, shade, column)

            fraction = reel.fraction
            for row in range(-1, rules.ROWS + 1):
                symbol = reel.symbol_at(row)
                cell = pygame.Rect(
                    column.x + 10,
                    int(WINDOW.y + (row - fraction) * CELL_HEIGHT) + 8,
                    CELL_WIDTH - 20, CELL_HEIGHT - 16,
                )
                highlighted = (index, row) in winning
                if highlighted:
                    pulse = anim.pulse(self._highlight_cycle, 6, 0.4, 1.0)
                    render.rounded_rect(surface, cell.inflate(6, 6),
                                        theme.with_alpha(theme.GOLD, int(60 * pulse)), 8)
                    render.rounded_rect(surface, cell.inflate(6, 6), theme.GOLD, 8, width=2)
                slotart.draw_symbol(surface, symbol, cell)
        surface.set_clip(clip)

        for index in range(1, rules.REELS):
            x = WINDOW.x + index * CELL_WIDTH
            pygame.draw.line(surface, theme.darken(theme.BG_DEEP, 0.2),
                             (x, WINDOW.y), (x, WINDOW.bottom), 2)

    def _winning_cells(self) -> set:
        if self.spinning or not self.result:
            return set()
        cells = set()
        for line_win in self.result.line_wins:
            cells.update(line_win.positions)
        if self.result.scatter_count >= 3:
            cells.update(self.result.scatter_positions)
        return cells

    def _draw_paytable(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(968, 96, 272, 430)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.small(bold=True), "PAYTABLE",
                    (box.centerx, box.y + 16), theme.GOLD, anchor="center")
        render.text(surface, self.fonts.tiny(), f"per line at {self.line_bet:,}/line",
                    (box.centerx, box.y + 36), theme.TEXT_MUTED, anchor="center")

        order = (rules.WILD, rules.SEVEN, rules.CROWN, rules.DIAMOND,
                 rules.HORSESHOE, rules.BELL, rules.LEMON, rules.CHERRY)
        y = box.y + 58
        for symbol in order:
            icon = pygame.Rect(box.x + 14, y, 34, 34)
            slotart.draw_symbol(surface, symbol, icon)
            pays = rules.PAYTABLE[symbol]
            for index, count in enumerate((3, 4, 5)):
                value = pays[index] * self.line_bet
                render.text(surface, self.fonts.tiny(), f"{count}x",
                            (box.x + 62 + index * 70, y + 6), theme.TEXT_MUTED)
                render.text(surface, self.fonts.tiny(bold=True), f"{value:,}",
                            (box.x + 62 + index * 70, y + 20), theme.TEXT)
            y += 40

        scatter_row = pygame.Rect(box.x + 14, y + 2, box.width - 28, 44)
        slotart.draw_symbol(surface, rules.SCATTER,
                            pygame.Rect(scatter_row.x, scatter_row.y, 32, 32))
        render.text(surface, self.fonts.tiny(), "3+ scatters anywhere",
                    (scatter_row.x + 42, scatter_row.y + 2), theme.TEXT_DIM)
        render.text(surface, self.fonts.tiny(bold=True),
                    f"pays {rules.SCATTER_PAYS[3]}x bet + {rules.FREE_SPIN_AWARD[3]} free spins",
                    (scatter_row.x + 42, scatter_row.y + 18), theme.GOLD)

    def _draw_win_panel(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(40, 118, 260, 160)
        render.panel(surface, box, theme.PANEL, theme.PANEL_EDGE, radius=12)
        render.text(surface, self.fonts.tiny(bold=True), "LAST WIN",
                    (box.x + 16, box.y + 14), theme.TEXT_DIM)
        colour = theme.GOLD if self.win_ticker.target else theme.TEXT_MUTED
        render.text(surface, self.fonts.title(bold=True), f"{self.win_ticker.value:,}",
                    (box.x + 16, box.y + 36), colour)

        if self.result and not self.spinning:
            lines = len(self.result.line_wins)
            detail = f"{lines} winning line{'s' if lines != 1 else ''}"
            if self.result.scatter_count >= 3:
                detail += f"  -  {self.result.scatter_count} scatters"
            render.text(surface, self.fonts.tiny(), detail,
                        (box.x + 16, box.y + 92), theme.TEXT_DIM)
            best = max(self.result.line_wins, key=lambda w: w.amount, default=None)
            if best:
                render.text(
                    surface, self.fonts.tiny(bold=True),
                    f"best: {best.count} x {rules.SYMBOL_NAMES[best.symbol]}",
                    (box.x + 16, box.y + 112), theme.TEXT,
                )
        stats = self.bank.stats_for(self.game_key)
        render.text(surface, self.fonts.tiny(), f"spins {stats.rounds:,}",
                    (box.x + 16, box.bottom - 24), theme.TEXT_MUTED)
        render.text(surface, self.fonts.tiny(), f"net {stats.net:+,}",
                    (box.right - 16, box.bottom - 24),
                    theme.WIN if stats.net > 0 else theme.LOSE, anchor="topright")

    def _draw_free_spin_banner(self, surface: pygame.Surface) -> None:
        if not self.machine.in_free_spins:
            return
        box = pygame.Rect(0, 0, 420, 40)
        box.center = (WINDOW.centerx, WINDOW.y - 38)
        pulse = anim.pulse(self.time, 4, 0.5, 1.0)
        render.glow(surface, box, theme.GOLD, radius=12, spread=14, alpha=int(90 * pulse))
        render.panel(surface, box, theme.PANEL, theme.GOLD, radius=12)
        render.text(
            surface, self.fonts.small(bold=True),
            f"FREE SPINS  -  {self.machine.free_spins} left  -  "
            f"all wins x{rules.FREE_SPIN_MULTIPLIER}",
            box.center, theme.GOLD, anchor="center",
        )
