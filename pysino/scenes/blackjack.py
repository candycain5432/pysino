"""Blackjack at a six deck shoe."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..games import blackjack as rules
from .base import BetControls, CardFlight, GameScene, draw_result_banner

CARD_SIZE = (86, 120)
SHOE_POSITION = (1120, 86)
DEALER_Y = 150
PLAYER_Y = 372
STACK_STEP = 32


class BlackjackScene(GameScene):
    title = "Blackjack"
    subtitle = "Blackjack pays 3:2  -  dealer stands on soft 17"
    game_key = "blackjack"
    default_bet = 25

    def __init__(self, app) -> None:
        super().__init__(app)
        self.game = rules.BlackjackGame(self.rng, rules.Rules(
            decks=config.BLACKJACK_DECKS,
            penetration=config.SHOE_PENETRATION,
            dealer_hits_soft_17=config.DEALER_HITS_SOFT_17,
        ))
        self.flight = CardFlight(SHOE_POSITION)
        self.bet_controls = BetControls(self, (40, 452))
        self.staked = 0
        self.hint: Optional[rules.Action] = None
        self._dealer_timer = 0.0
        self._pending_dealer = False

        self._build_buttons()
        self._refresh_buttons()

    # ------------------------------------------------------------ widgets --
    def _build_buttons(self) -> None:
        rects = ui.centred_row(config.BASE_WIDTH // 2, 600, 132, 50, 5, gap=12)
        self.action_buttons: Dict[rules.Action, ui.Button] = {}
        specs = [
            (rules.Action.HIT, "Hit", pygame.K_h, "H", ui.SECONDARY),
            (rules.Action.STAND, "Stand", pygame.K_s, "S", ui.SECONDARY),
            (rules.Action.DOUBLE, "Double", pygame.K_d, "D", ui.SECONDARY),
            (rules.Action.SPLIT, "Split", pygame.K_p, "P", ui.SECONDARY),
            (rules.Action.SURRENDER, "Surrender", pygame.K_r, "R", ui.GHOST),
        ]
        for rect, (action, label, key, badge, style) in zip(rects, specs):
            button = ui.Button(rect, label, lambda a=action: self._act(a), style, key, badge)
            self.action_buttons[action] = button
            self.add(button)

        self.deal_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 100, 600, 200, 50), "Deal",
            self._deal, ui.PRIMARY, pygame.K_SPACE, "SPACE",
        )
        self.add(self.deal_button)

        self.insurance_buttons = [
            ui.Button(pygame.Rect(config.BASE_WIDTH // 2 - 160, 470, 150, 46),
                      "Insurance", self._take_insurance, ui.PRIMARY, pygame.K_y, "Y"),
            ui.Button(pygame.Rect(config.BASE_WIDTH // 2 + 10, 470, 150, 46),
                      "No thanks", self._decline_insurance, ui.GHOST, pygame.K_n, "N"),
        ]
        for button in self.insurance_buttons:
            self.add(button)

        self.hint_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH - 190, 600, 150, 50), "Hint",
            self._show_hint, ui.GHOST, pygame.K_TAB, "TAB",
        )
        self.add(self.hint_button)

    def _refresh_buttons(self) -> None:
        state = self.game.state
        betting = state in (rules.State.BETTING, rules.State.DONE)
        playing = state is rules.State.PLAYER and not self.flight.busy
        insuring = state is rules.State.INSURANCE

        self.deal_button.visible = betting
        self.deal_button.enabled = betting and self.can_afford() and not self.flight.busy
        self.bet_controls.set_enabled(betting)

        available = set(self.game.available_actions()) if playing else set()
        for action, button in self.action_buttons.items():
            button.visible = playing
            affordable = True
            if action is rules.Action.DOUBLE and self.game.active_hand:
                affordable = self.bank.can_afford(self.game.active_hand.bet)
            if action is rules.Action.SPLIT and self.game.active_hand:
                affordable = self.bank.can_afford(self.game.active_hand.bet)
            button.enabled = action in available and affordable

        for button in self.insurance_buttons:
            button.visible = insuring
        self.insurance_buttons[0].enabled = (
            insuring and self.bank.can_afford(self.game.insurance_cost)
        )
        self.hint_button.visible = playing

    # ------------------------------------------------------------ actions --
    def _deal(self) -> None:
        if self.game.state not in (rules.State.BETTING, rules.State.DONE):
            return
        bet = self.clamp_bet(self.bet)
        if not self.wager(bet):
            return
        self.bet = bet
        self.staked = bet
        self.hint = None
        self.last_result_text = ""
        self.flight.reset()
        if self.game.shoe.needs_shuffle:
            self.audio.play("shuffle")
            self.toast("Shuffling the shoe", theme.TEXT_DIM, 1.6)
        self.game.start_round(bet)
        self.audio.play("deal")
        self._after_state_change()

    def _act(self, action: rules.Action) -> None:
        if self.game.state is not rules.State.PLAYER:
            return
        if action not in self.game.available_actions():
            return
        self.hint = None

        if action is rules.Action.DOUBLE:
            hand = self.game.active_hand
            if not self.bank.can_afford(hand.bet):
                self.toast("Not enough chips to double", theme.LOSE)
                return
            extra, _ = self.game.double()
            self.bank.wager(self.game_key, extra)
            self.staked += extra
            self.audio.play("chip")
        elif action is rules.Action.SPLIT:
            hand = self.game.active_hand
            if not self.bank.can_afford(hand.bet):
                self.toast("Not enough chips to split", theme.LOSE)
                return
            extra = self.game.split()
            self.bank.wager(self.game_key, extra)
            self.staked += extra
            self.audio.play("chip")
        elif action is rules.Action.HIT:
            self.game.hit()
            self.audio.play("deal")
        elif action is rules.Action.STAND:
            self.game.stand()
            self.audio.play("click")
        else:
            self.game.surrender()
            self.audio.play("back")
        self._after_state_change()

    def _take_insurance(self) -> None:
        cost = self.game.insurance_cost
        if not self.bank.can_afford(cost):
            return
        self.game.take_insurance()
        self.bank.wager(self.game_key, cost)
        self.staked += cost
        self.audio.play("chip")
        self._after_state_change()

    def _decline_insurance(self) -> None:
        self.game.decline_insurance()
        self.audio.play("click")
        self._after_state_change()

    def _show_hint(self) -> None:
        hand = self.game.active_hand
        if hand and self.game.dealer_upcard:
            self.hint = rules.basic_strategy(
                hand, self.game.dealer_upcard, self.game.available_actions()
            )
            self.audio.play("select")

    def _after_state_change(self) -> None:
        if self.game.state is rules.State.DONE and self.game.result:
            self._pending_dealer = True
            self._dealer_timer = 0.55
        self._refresh_buttons()

    def _finish_round(self) -> None:
        result = self.game.result
        if not result:
            return
        self.award(result.returned)
        net = self.settle(result.staked, result.returned,
                          celebrate_at=(config.BASE_WIDTH // 2, PLAYER_Y))
        for hand in result.hands:
            if hand.is_blackjack:
                self.bank.unlock("natural")
            if hand.is_charlie:
                self.bank.unlock("five_card")
        self.rng.next_round()
        self._refresh_buttons()

    # ------------------------------------------------------------- layout --
    def _dealer_positions(self) -> List[Tuple[int, int]]:
        count = len(self.game.dealer_cards)
        total = max(0, (count - 1)) * STACK_STEP + CARD_SIZE[0]
        start = config.BASE_WIDTH // 2 - total // 2
        return [(start + index * STACK_STEP, DEALER_Y) for index in range(count)]

    def _hand_origins(self) -> List[int]:
        hands = self.game.hands or [rules.Hand()]
        widths = [
            max(0, len(hand.cards) - 1) * STACK_STEP + CARD_SIZE[0] for hand in hands
        ]
        gap = 46
        total = sum(widths) + gap * (len(hands) - 1)
        x = config.BASE_WIDTH // 2 - total // 2
        origins = []
        for width in widths:
            origins.append(x)
            x += width + gap
        return origins

    def _sync_flight(self) -> None:
        targets = []
        for index, position in enumerate(self._dealer_positions()):
            face_up = not (index == 1 and self.game.hole_hidden)
            targets.append((("d", index), position, face_up))
        for hand_index, (hand, origin) in enumerate(zip(self.game.hands, self._hand_origins())):
            for card_index in range(len(hand.cards)):
                targets.append((
                    ("p", hand_index, card_index),
                    (origin + card_index * STACK_STEP, PLAYER_Y),
                    True,
                ))
        self.flight.sync(targets)

    # -------------------------------------------------------------- frame --
    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._sync_flight()
        self.flight.update(dt)
        if self._pending_dealer:
            self._dealer_timer -= dt
            if self._dealer_timer <= 0 and not self.flight.busy:
                self._pending_dealer = False
                self._finish_round()
        self._refresh_buttons()

    # --------------------------------------------------------------- draw --
    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_table_markings(surface)
        self._draw_shoe(surface)
        self._draw_dealer(surface)
        self._draw_hands(surface)
        self.bet_controls.draw(surface)
        self._draw_side_panel(surface)
        if self.game.state is rules.State.INSURANCE:
            self._draw_insurance_prompt(surface)
        if self.game.state is rules.State.DONE and self.game.result and not self._pending_dealer:
            self._draw_outcome(surface)
        if self.is_broke and self.game.state in (rules.State.BETTING, rules.State.DONE):
            self._draw_broke(surface)

    def _draw_table_markings(self, surface: pygame.Surface) -> None:
        arc = pygame.Rect(config.BASE_WIDTH // 2 - 430, 196, 860, 330)
        pygame.draw.arc(surface, theme.GOLD_DIM, arc, 3.34, 6.08, 2)
        render.text(surface, self.fonts.small(bold=True),
                    "BLACKJACK PAYS 3 TO 2", (config.BASE_WIDTH // 2, 318),
                    theme.GOLD_DIM, anchor="center")
        render.text(surface, self.fonts.tiny(),
                    "Dealer must draw to 16 and stand on all 17s",
                    (config.BASE_WIDTH // 2, 340), theme.mix(theme.GOLD_DIM, theme.FELT, 0.4),
                    anchor="center")

    def _draw_shoe(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(SHOE_POSITION[0] - 6, SHOE_POSITION[1] - 8, 98, 128)
        render.panel(surface, box, theme.WOOD, theme.WOOD_LIGHT, radius=8)
        back = cardrender.card_back((78, 108))
        surface.blit(back, (box.x + 10, box.y + 10))
        remaining = self.game.shoe.cards_remaining / max(1, self.game.shoe.total_cards)
        meter = pygame.Rect(box.x, box.bottom + 8, box.width, 6)
        render.rounded_rect(surface, meter, theme.PANEL, 3)
        render.rounded_rect(surface, pygame.Rect(meter.x, meter.y,
                                                 int(meter.width * remaining), meter.height),
                            theme.GOLD, 3)
        render.text(surface, self.fonts.tiny(), f"{self.game.shoe.cards_remaining} cards",
                    (box.centerx, meter.bottom + 12), theme.TEXT_MUTED, anchor="center")

    def _draw_dealer(self, surface: pygame.Surface) -> None:
        cards = self.game.dealer_cards
        if not cards:
            return
        for index, card in enumerate(cards):
            self.flight.draw_card(surface, ("d", index), card, CARD_SIZE)

        if not self.game.hole_hidden:
            total = self.game.dealer_total
            label = "Bust" if total > 21 else str(total)
            if self.game.dealer_has_blackjack:
                label = "Blackjack"
        else:
            label = str(self.game.dealer_upcard.blackjack_value) if cards else ""
        self._draw_total_badge(surface, (config.BASE_WIDTH // 2, DEALER_Y - 26), label,
                               theme.LOSE if self.game.dealer_total > 21 else theme.TEXT)

    def _draw_hands(self, surface: pygame.Surface) -> None:
        origins = self._hand_origins()
        for hand_index, (hand, origin) in enumerate(zip(self.game.hands, origins)):
            active = (
                self.game.state is rules.State.PLAYER
                and hand_index == self.game.active_index
            )
            width = max(0, len(hand.cards) - 1) * STACK_STEP + CARD_SIZE[0]
            if active:
                marker = pygame.Rect(origin - 10, PLAYER_Y - 10, width + 20, CARD_SIZE[1] + 20)
                render.glow(surface, marker, theme.GOLD,
                            radius=12, spread=14,
                            alpha=int(70 + 50 * anim.pulse(self.time, 4)))
            for card_index, card in enumerate(hand.cards):
                highlight = None
                if hand.outcome is rules.Outcome.BLACKJACK:
                    highlight = theme.GOLD
                self.flight.draw_card(
                    surface, ("p", hand_index, card_index), card, CARD_SIZE,
                    highlight=highlight,
                    dim=hand.is_busted or hand.surrendered,
                )
            centre = (origin + width // 2, PLAYER_Y + CARD_SIZE[1] + 26)
            colour = theme.TEXT
            if hand.is_busted:
                colour = theme.LOSE
            elif hand.is_blackjack:
                colour = theme.GOLD
            self._draw_total_badge(surface, centre, hand.label(), colour)

            chip_at = (origin + width // 2, PLAYER_Y + CARD_SIZE[1] + 62)
            self._draw_bet_chips(surface, chip_at, hand.bet)

            if hand.outcome and self.game.state is rules.State.DONE:
                self._draw_hand_outcome(surface, hand, (origin + width // 2, PLAYER_Y - 24))

    def _draw_total_badge(self, surface, centre, label: str, colour) -> None:
        if not label:
            return
        font = self.fonts.small(bold=True)
        width = font.size(label)[0] + 26
        box = pygame.Rect(0, 0, width, 26)
        box.center = centre
        render.rounded_rect(surface, box, theme.with_alpha(theme.BG_DEEP, 210), 13)
        render.rounded_rect(surface, box, colour, 13, width=1)
        render.text(surface, font, label, box.center, colour, anchor="center")

    def _draw_bet_chips(self, surface, centre, amount: int) -> None:
        if amount <= 0:
            return
        pieces = cardrender.chips_for_amount(amount, config.CHIP_DENOMINATIONS)
        x = centre[0] - (len(pieces) - 1) * 15
        for denomination, count in pieces[:4]:
            cardrender.draw_chip_stack(surface, (x, centre[1]), denomination,
                                       min(count, 4), radius=14, spacing=3)
            x += 30
        render.text(surface, self.fonts.tiny(bold=True), f"{amount:,}",
                    (centre[0], centre[1] + 24), theme.GOLD, anchor="center")

    def _draw_hand_outcome(self, surface, hand: rules.Hand, centre) -> None:
        text_map = {
            rules.Outcome.BLACKJACK: ("BLACKJACK", theme.GOLD),
            rules.Outcome.WIN: ("WIN", theme.WIN),
            rules.Outcome.PUSH: ("PUSH", theme.PUSH),
            rules.Outcome.LOSE: ("LOSE", theme.LOSE),
            rules.Outcome.BUST: ("BUST", theme.LOSE),
            rules.Outcome.SURRENDER: ("SURRENDER", theme.TEXT_DIM),
        }
        label, colour = text_map[hand.outcome]
        self._draw_total_badge(surface, centre, label, colour)

    def _draw_insurance_prompt(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(0, 0, 420, 120)
        box.center = (config.BASE_WIDTH // 2, 424)
        render.panel(surface, box, theme.PANEL, theme.GOLD, radius=14)
        render.text(surface, self.fonts.body(bold=True), "Dealer shows an Ace",
                    (box.centerx, box.y + 28), theme.TEXT, anchor="center")
        render.text(surface, self.fonts.small(),
                    f"Insurance costs {self.game.insurance_cost:,} and pays 2:1",
                    (box.centerx, box.y + 54), theme.TEXT_DIM, anchor="center")

    def _draw_outcome(self, surface: pygame.Surface) -> None:
        if not self.last_result_text:
            return
        result = self.game.result
        subtitle = ""
        if result and result.insurance_payout:
            subtitle = f"insurance paid {result.insurance_payout:,}"
        draw_result_banner(surface, self.last_result_text, self.last_result_color,
                           (config.BASE_WIDTH // 2, 318), subtitle)

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        stats = self.bank.stats_for(self.game_key)
        box = pygame.Rect(40, 96, 210, 132)
        render.panel(surface, box, theme.with_alpha(theme.PANEL, 180), theme.PANEL_EDGE,
                     radius=10, alpha=200)
        rows = [
            ("Hands", f"{stats.rounds:,}"),
            ("Won", f"{stats.wins:,}"),
            ("Net", f"{stats.net:+,}"),
        ]
        for index, (label, value) in enumerate(rows):
            row = pygame.Rect(box.x + 14, box.y + 14 + index * 26, box.width - 28, 22)
            colour = theme.TEXT
            if label == "Net":
                colour = theme.WIN if stats.net > 0 else theme.LOSE if stats.net < 0 else theme.TEXT
            render.text(surface, self.fonts.tiny(), label, (row.x, row.centery),
                        theme.TEXT_DIM, anchor="midleft")
            render.text(surface, self.fonts.tiny(bold=True), value, (row.right, row.centery),
                        colour, anchor="midright")
        if self.hint:
            hint_box = pygame.Rect(box.x, box.bottom - 34, box.width, 26)
            render.text(surface, self.fonts.tiny(bold=True),
                        f"Basic strategy: {self.hint.value.upper()}",
                        hint_box.center, theme.GOLD, anchor="center")

    def _draw_broke(self, surface: pygame.Surface) -> None:
        self.draw_bailout_prompt(surface)
        if not hasattr(self, "_bailout_button"):
            self._bailout_button = ui.Button(
                pygame.Rect(config.BASE_WIDTH // 2 - 90, config.BASE_HEIGHT // 2 + 28,
                            180, 44),
                "Take the stake", self._bailout, ui.PRIMARY,
            )
            self.add(self._bailout_button)
        self._bailout_button.visible = True
        self._bailout_button.enabled = True

    def _bailout(self) -> None:
        amount = self.bank.claim_bailout()
        if amount:
            self.audio.play("cash")
            self.toast(f"The house stakes you {amount:,} chips", theme.GOLD)
            self._bailout_button.visible = False
