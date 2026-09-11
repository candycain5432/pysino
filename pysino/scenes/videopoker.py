"""Jacks or Better video poker, 9/6 full pay."""

from __future__ import annotations

from typing import List, Optional

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..games import videopoker as rules
from .base import CardFlight, GameScene, draw_result_banner

CARD_SIZE = (124, 172)
CARD_Y = 330
CARD_GAP = 18
DECK_POSITION = (1120, 120)


class VideoPokerScene(GameScene):
    title = "Video Poker"
    subtitle = "Jacks or Better  -  9/6 full pay  -  99.5% back"
    game_key = "videopoker"
    default_bet = 50
    #: Class-level defaults so the inherited ``bet`` setter has something to
    #: work with while the base scene is still constructing; the saved values
    #: are applied straight after.
    coins = rules.MAX_COINS
    coin_value = 10

    def __init__(self, app) -> None:
        super().__init__(app)
        self.game = rules.VideoPokerGame(rng=self.rng)
        self.flight = CardFlight(DECK_POSITION, duration=0.26, stagger=0.07)
        self.coins = int(self.bank.settings.get("vp_coins", rules.MAX_COINS) or rules.MAX_COINS)
        self.coin_value = int(self.bank.settings.get("vp_coin_value", 10) or 10)
        self.advice: Optional[tuple] = None
        self._build_widgets()

    # ------------------------------------------------------------ widgets --
    def _build_widgets(self) -> None:
        self.hold_buttons: List[ui.Button] = []
        keys = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5)
        for index in range(5):
            rect = pygame.Rect(self._card_x(index), CARD_Y + CARD_SIZE[1] + 16,
                               CARD_SIZE[0], 42)
            button = ui.Button(rect, "HOLD", lambda i=index: self._toggle(i),
                               ui.GHOST, keys[index], str(index + 1),
                               font=self.fonts.small(bold=True), radius=8)
            self.hold_buttons.append(button)
            self.add(button)

        self.deal_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 110, 622, 220, 54), "Deal",
            self._deal_or_draw, ui.PRIMARY, pygame.K_SPACE, "SPACE",
            font=self.fonts.large(bold=True),
        )
        self.add(self.deal_button)

        self.bet_down = ui.Button(pygame.Rect(300, 632, 44, 36), "-",
                                  self._bet_down, ui.GHOST, radius=6)
        self.bet_up = ui.Button(pygame.Rect(430, 632, 44, 36), "+",
                                self._bet_up, ui.GHOST, radius=6)
        self.max_button = ui.Button(pygame.Rect(160, 632, 120, 36), "Max Coins",
                                    self._max_coins, ui.SECONDARY, pygame.K_m, "M",
                                    font=self.fonts.tiny(bold=True), radius=6)
        self.hint_button = ui.Button(pygame.Rect(config.BASE_WIDTH - 200, 632, 150, 36),
                                     "Hint", self._hint, ui.GHOST, pygame.K_TAB, "TAB",
                                     font=self.fonts.tiny(bold=True), radius=6)
        for button in (self.bet_down, self.bet_up, self.max_button, self.hint_button):
            self.add(button)

    def _card_x(self, index: int) -> int:
        total = 5 * CARD_SIZE[0] + 4 * CARD_GAP
        start = config.BASE_WIDTH // 2 - total // 2
        return start + index * (CARD_SIZE[0] + CARD_GAP)

    # ------------------------------------------------------------ betting --
    @property
    def bet(self) -> int:
        return self.coins * self.coin_value

    @bet.setter
    def bet(self, value: int) -> None:
        # The stake is driven by coins, so a plain assignment maps onto the
        # nearest affordable coin value.
        self.coin_value = max(1, int(value) // max(1, self.coins))

    def _bet_up(self) -> None:
        steps = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1_000)
        for step in steps:
            if step > self.coin_value:
                self.coin_value = step
                break
        self.audio.play("chip")

    def _bet_down(self) -> None:
        steps = (1, 2, 5, 10, 25, 50, 100, 250, 500, 1_000)
        for step in reversed(steps):
            if step < self.coin_value:
                self.coin_value = step
                break
        self.audio.play("chip")

    def _max_coins(self) -> None:
        self.coins = rules.MAX_COINS
        self.audio.play("chip")

    # ------------------------------------------------------------ actions --
    def _deal_or_draw(self) -> None:
        if self.game.state is rules.State.HOLDING:
            self._draw()
        else:
            self._deal()

    def _deal(self) -> None:
        stake = self.bet
        if not self.bank.can_afford(stake):
            self.toast("Not enough chips", theme.LOSE)
            return
        if not self.wager(stake):
            return
        self.advice = None
        self.last_result_text = ""
        self.flight.reset()
        self.game.deal(self.coins, self.coin_value)
        self.audio.play("deal")

    def _draw(self) -> None:
        payout = self.game.draw()
        self.advice = None
        self.audio.play("flip")
        self.award(payout)
        self.settle(self.bet, payout, celebrate_at=(config.BASE_WIDTH // 2, CARD_Y + 80))
        if self.game.result == rules.ROYAL_FLUSH:
            self.bank.unlock("royal")
            self.audio.play("jackpot")
        elif self.game.result == rules.FOUR_OF_A_KIND:
            self.bank.unlock("quads")
        if self.game.result:
            self.last_result_text = rules.HAND_NAMES[self.game.result]
        else:
            self.last_result_text = "No pair"
        self.bank.settings["vp_coins"] = self.coins
        self.bank.settings["vp_coin_value"] = self.coin_value
        self.rng.next_round()

    def _toggle(self, index: int) -> None:
        if self.game.state is not rules.State.HOLDING:
            return
        self.game.toggle_hold(index)
        self.audio.play("click")

    def _hint(self) -> None:
        if self.game.state is not rules.State.HOLDING:
            return
        self.advice = rules.best_hold(self.game.cards, self.rng, samples=250)
        self.game.set_holds(self.advice)
        self.audio.play("select")
        self.toast("Holds set to the best play", theme.GOLD, 1.8)

    # -------------------------------------------------------------- frame --
    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        targets = [
            ((index,), (self._card_x(index), CARD_Y), True)
            for index in range(len(self.game.cards))
        ]
        self.flight.sync(targets)
        self.flight.update(dt)

        holding = self.game.state is rules.State.HOLDING
        for index, button in enumerate(self.hold_buttons):
            button.visible = holding
            button.style = ui.PRIMARY if (holding and self.game.held[index]) else ui.GHOST
        self.deal_button.label = "Draw" if holding else "Deal"
        self.deal_button.enabled = holding or self.bank.can_afford(self.bet)
        for button in (self.bet_up, self.bet_down, self.max_button):
            button.enabled = not holding
        self.hint_button.visible = holding

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (18, 34, 62), theme.BG_DEEP)
        render.vignette(surface, 170)

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_paytable(surface)
        self._draw_cards(surface)
        self._draw_bet_strip(surface)
        if self.game.state is rules.State.COMPLETE and self.last_result_text:
            colour = theme.GOLD if self.game.result else theme.TEXT_DIM
            draw_result_banner(surface, self.last_result_text, colour,
                               (config.BASE_WIDTH // 2, 268),
                               f"+{self.game.payout:,}" if self.game.payout else "", width=420)

    def _draw_paytable(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(config.BASE_WIDTH // 2 - 360, 76, 720, 172)
        render.panel(surface, box, theme.PANEL, theme.GOLD_DIM, radius=12)

        column_width = 78
        first = box.x + 250
        for coin in range(1, rules.MAX_COINS + 1):
            highlighted = coin == self.coins
            header = pygame.Rect(first + (coin - 1) * column_width, box.y + 8,
                                 column_width, 20)
            if highlighted:
                render.rounded_rect(surface, pygame.Rect(header.x, box.y + 6,
                                                         column_width, box.height - 12),
                                    theme.darken(theme.GOLD, 0.78), 6)
            render.text(surface, self.fonts.tiny(bold=True), str(coin),
                        header.center, theme.GOLD if highlighted else theme.TEXT_MUTED,
                        anchor="center")

        for index, hand in enumerate(rules.PAY_ORDER):
            y = box.y + 32 + index * 15
            winner = self.game.result == hand and self.game.state is rules.State.COMPLETE
            colour = theme.GOLD if winner else theme.TEXT_DIM
            render.text(surface, self.fonts.tiny(bold=winner), rules.HAND_NAMES[hand],
                        (box.x + 16, y), colour)
            for coin in range(1, rules.MAX_COINS + 1):
                value = rules.PAYTABLE[hand][coin - 1]
                emphasis = coin == self.coins
                render.text(
                    surface, self.fonts.tiny(bold=winner or emphasis), f"{value:,}",
                    (first + (coin - 1) * column_width + column_width // 2, y),
                    theme.GOLD if (winner or emphasis) else theme.TEXT_MUTED,
                    anchor="midtop",
                )

    def _draw_cards(self, surface: pygame.Surface) -> None:
        for index, card in enumerate(self.game.cards):
            held = self.game.held[index]
            highlight = theme.GOLD if held else None
            rect = self.flight.draw_card(surface, (index,), card, CARD_SIZE,
                                         highlight=highlight)
            if held and rect:
                badge = pygame.Rect(0, 0, 68, 24)
                badge.midtop = (rect.centerx, rect.y + 40)
                render.rounded_rect(surface, badge, theme.GOLD, 12)
                render.text(surface, self.fonts.tiny(bold=True), "HELD", badge.center,
                            theme.INK, anchor="center")
            if self.advice and rect and self.advice[index] and not held:
                pygame.draw.rect(surface, theme.INFO, rect.inflate(8, 8), 2, border_radius=8)

    def _draw_bet_strip(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(40, 560, config.BASE_WIDTH - 80, 56)
        render.panel(surface, box, theme.with_alpha(theme.PANEL, 200), theme.PANEL_EDGE,
                     radius=10, alpha=210)
        render.text(surface, self.fonts.tiny(bold=True), "COINS",
                    (box.x + 20, box.y + 10), theme.TEXT_DIM)
        for coin in range(1, rules.MAX_COINS + 1):
            spot = (box.x + 30 + (coin - 1) * 26, box.y + 38)
            filled = coin <= self.coins
            render.circle(surface, spot, 9, theme.GOLD if filled else theme.PANEL_LIGHT)
            if filled:
                render.circle(surface, spot, 9, theme.GOLD_BRIGHT, 1)

        render.text(surface, self.fonts.tiny(bold=True), "COIN VALUE",
                    (box.x + 200, box.y + 10), theme.TEXT_DIM)
        render.text(surface, self.fonts.body(bold=True), f"{self.coin_value:,}",
                    (box.x + 372, box.y + 30), theme.TEXT, anchor="center")

        render.text(surface, self.fonts.tiny(bold=True), "TOTAL BET",
                    (box.x + 520, box.y + 10), theme.TEXT_DIM)
        render.text(surface, self.fonts.body(bold=True), f"{self.bet:,}",
                    (box.x + 520, box.y + 26), theme.GOLD)

        stats = self.bank.stats_for(self.game_key)
        render.text(surface, self.fonts.tiny(), f"hands {stats.rounds:,}",
                    (box.right - 20, box.y + 12), theme.TEXT_MUTED, anchor="topright")
        render.text(surface, self.fonts.tiny(), f"net {stats.net:+,}",
                    (box.right - 20, box.y + 32), theme.TEXT_MUTED, anchor="topright")
