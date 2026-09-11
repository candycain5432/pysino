"""No-limit Texas Hold'em against three bots.

The player's seat is backed directly by the shared chip bank: every chip they
push into the pot leaves the bank at that moment, and anything they win comes
straight back, so the stack in the HUD is always the truth.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

from .. import config
from ..core import anim, cardrender, render, theme, ui
from ..games import holdem as rules
from .base import CardFlight, GameScene

HOLE_SIZE = (66, 92)
BOARD_SIZE = (82, 114)
BOARD_Y = 272
#: Where each seat's committed chips sit, kept clear of the name plates.
CHIP_ANCHORS = {0: (782, 452), 1: (300, 262), 2: (800, 150), 3: (980, 262)}
DECK_POSITION = (620, 96)

SMALL_BLIND = 10
BIG_BLIND = 20
BOT_STACK = 2_000
#: The player may bring at most this much to the table in one sitting.
MAX_BUY_IN = 5_000


class HoldemScene(GameScene):
    title = "Texas Hold'em"
    subtitle = f"No-limit cash game  -  blinds {SMALL_BLIND}/{BIG_BLIND}"
    game_key = "holdem"

    def __init__(self, app) -> None:
        super().__init__(app)
        self.players = rules.make_table(self.rng, human_stack=0, bot_count=3,
                                        bot_stack=BOT_STACK)
        self.human = self.players[0]
        self.game = rules.HoldemGame(self.rng, self.players, SMALL_BLIND, BIG_BLIND)
        self.flight = CardFlight(DECK_POSITION, duration=0.26, stagger=0.06)

        self._tracked_committed = 0
        self._think_timer = 0.0
        self._result_timer = 0.0
        #: Guards the pay-out so a finished hand is booked exactly once, no
        #: matter whether the player or a bot made the closing action.
        self._hand_booked = True
        self._raise_amount = BIG_BLIND * 2
        self._seat_positions = self._build_seats()
        self._build_widgets()

    # ------------------------------------------------------------- set-up --
    def _build_seats(self) -> Dict[int, Tuple[int, int]]:
        return {
            0: (config.BASE_WIDTH // 2, 452),
            1: (168, 262),
            2: (config.BASE_WIDTH // 2, 116),
            3: (config.BASE_WIDTH - 168, 262),
        }

    def _build_widgets(self) -> None:
        rects = ui.button_row(352, 620, 132, 50, 3, gap=12)
        self.fold_button = ui.Button(rects[0], "Fold", lambda: self._act(rules.Action.FOLD),
                                     ui.DANGER, pygame.K_f, "F")
        # Check and Call occupy the same slot; exactly one is ever visible.
        self.check_button = ui.Button(rects[1], "Check",
                                      lambda: self._act(rules.Action.CHECK),
                                      ui.SECONDARY, pygame.K_c, "C")
        self.call_button = ui.Button(rects[1], "Call", lambda: self._act(rules.Action.CALL),
                                     ui.SECONDARY, pygame.K_c, "C")
        self.raise_button = ui.Button(rects[2], "Raise", self._raise, ui.PRIMARY,
                                      pygame.K_r, "R")
        for button in (self.fold_button, self.check_button, self.call_button,
                       self.raise_button):
            self.add(button)

        self.raise_slider = ui.Slider(
            pygame.Rect(352, 588, 420, 24), BIG_BLIND, BIG_BLIND * 10, self._raise_amount,
            self._set_raise, step=1, formatter=lambda value: f"raise to {int(value):,}",
        )
        self.add(self.raise_slider)

        presets = ui.button_row(790, 620, 78, 50, 3, gap=8)
        self.preset_buttons = [
            ui.Button(presets[0], "1/2 Pot", lambda: self._preset(0.5), ui.GHOST,
                      font=self.fonts.tiny(bold=True), radius=6),
            ui.Button(presets[1], "Pot", lambda: self._preset(1.0), ui.GHOST,
                      font=self.fonts.tiny(bold=True), radius=6),
            ui.Button(presets[2], "All In", lambda: self._preset(99.0), ui.GHOST,
                      font=self.fonts.tiny(bold=True), radius=6),
        ]
        for button in self.preset_buttons:
            self.add(button)

        self.next_button = ui.Button(
            pygame.Rect(config.BASE_WIDTH // 2 - 110, 620, 220, 50), "Next Hand",
            self._start_hand, ui.PRIMARY, pygame.K_SPACE, "SPACE",
        )
        self.add(self.next_button)

    # ---------------------------------------------------------- lifecycle --
    def on_enter(self, **kwargs) -> None:
        self._start_hand()

    def on_exit(self) -> None:
        # Leaving mid-hand forfeits whatever is already in the pot, which is
        # exactly what standing up from a live table means.
        self._sync_commitment()
        super().on_exit()

    @property
    def _hand_live(self) -> bool:
        return not self.game.is_hand_over

    # ------------------------------------------------------------- chips --
    def _sync_commitment(self) -> None:
        """Mirror whatever the player has pushed into the pot out of the bank."""
        delta = self.human.committed - self._tracked_committed
        if delta > 0:
            take = min(delta, self.bank.chips)
            if take > 0:
                self.bank.wager(self.game_key, take)
            self._tracked_committed = self.human.committed

    def _start_hand(self) -> None:
        if self._hand_live:
            return
        if self.bank.chips < BIG_BLIND:
            self.toast("You need at least one big blind to sit down", theme.LOSE)
            return

        # Re-seat the player with their whole (capped) bankroll each hand.
        # This is a mirror of the bank, not a second pot of chips.
        self.human.chips = min(self.bank.chips, MAX_BUY_IN)
        for bot in self.players[1:]:
            if bot.chips < BIG_BLIND:
                bot.chips = BOT_STACK
        self._tracked_committed = 0
        self.flight.reset()
        self.last_result_text = ""
        self.game.start_hand()
        self._hand_booked = False
        self._sync_commitment()
        self.audio.play("deal")
        self._think_timer = 0.8

    def _finish_hand(self) -> None:
        result = self.game.result
        if result is None:
            return
        self._hand_booked = True
        self._sync_commitment()
        staked = self.human.committed
        won = self.human.won_last
        if won:
            self.bank.award(self.game_key, won)
        self.settle(staked, won, celebrate_at=(config.BASE_WIDTH // 2, BOARD_Y + 60))

        if result.went_to_showdown:
            for entry in result.entries:
                if entry.player is self.human and entry.rank:
                    from ..core import poker

                    if entry.rank.category == poker.STRAIGHT_FLUSH and \
                            entry.rank.tiebreakers[0] == 14:
                        self.bank.unlock("royal")
                    elif entry.rank.category == poker.FOUR_OF_A_KIND:
                        self.bank.unlock("quads")
                    self.last_result_text = entry.rank.describe()
        elif self.human in result.winners:
            self.last_result_text = "Everyone folded"

        # No refund is due here: the bank was only ever debited for chips the
        # player actually committed, and ``human.chips`` is a display mirror
        # that gets re-seated from the bank at the start of the next hand.
        self._result_timer = 3.2
        self.rng.next_round()

    # ------------------------------------------------------------ actions --
    def _set_raise(self, value: float) -> None:
        self._raise_amount = int(value)

    def _preset(self, fraction: float) -> None:
        if not self._is_human_turn:
            return
        pot = self.game.pot
        owed = self.game.to_call(self.human)
        if fraction >= 10:
            target = self.game.max_raise_to(self.human)
        else:
            target = int((pot + owed) * fraction) + self.human.bet + owed
        low = self.game.min_raise_to(self.human)
        high = self.game.max_raise_to(self.human)
        self._raise_amount = max(low, min(target, high))
        self.raise_slider.value = self._raise_amount
        self.audio.play("click")

    def _raise(self) -> None:
        self._act(rules.Action.RAISE, self._raise_amount)

    def _act(self, action: rules.Action, amount: int = 0) -> None:
        if not self._is_human_turn:
            return
        legal = self.game.legal_actions(self.human)
        if action is rules.Action.RAISE and rules.Action.BET in legal:
            action = rules.Action.BET
        if action not in legal:
            return
        self.game.act(action, amount)
        self._sync_commitment()
        self.audio.play({"fold": "back", "check": "click"}.get(action.value, "chip"))
        self._think_timer = 0.7

    @property
    def _is_human_turn(self) -> bool:
        return (
            self._hand_live
            and self.game.current_player is self.human
            and not self.flight.busy
        )

    # -------------------------------------------------------------- frame --
    def update(self, dt: float, mouse_pos) -> None:
        super().update(dt, mouse_pos)
        self._sync_flight()
        self.flight.update(dt)

        if not self.game.is_hand_over:
            current = self.game.current_player
            if current is not None and not current.is_human:
                self._think_timer -= dt
                if self._think_timer <= 0 and not self.flight.busy:
                    self.game.play_ai_turn()
                    self.audio.play("chip")
                    self._think_timer = 0.75

        # Book the result from here rather than inside the branch above: the
        # closing action is just as often the player's as a bot's.
        if self.game.is_hand_over:
            if not self._hand_booked:
                self._finish_hand()
            else:
                self._result_timer = max(0.0, self._result_timer - dt)

        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        human_turn = self._is_human_turn
        legal = self.game.legal_actions(self.human) if human_turn else []
        owed = self.game.to_call(self.human) if human_turn else 0

        self.fold_button.visible = human_turn
        self.fold_button.enabled = rules.Action.FOLD in legal
        self.check_button.visible = human_turn and owed == 0
        self.check_button.enabled = rules.Action.CHECK in legal
        self.call_button.visible = human_turn and owed > 0
        self.call_button.enabled = rules.Action.CALL in legal
        self.call_button.label = f"Call {owed:,}"

        can_raise = rules.Action.RAISE in legal or rules.Action.BET in legal
        self.raise_button.visible = human_turn
        self.raise_button.enabled = can_raise
        self.raise_button.label = "Bet" if rules.Action.BET in legal else "Raise"
        self.raise_slider.visible = human_turn and can_raise
        for button in self.preset_buttons:
            button.visible = human_turn and can_raise

        if human_turn and can_raise:
            low = self.game.min_raise_to(self.human)
            high = self.game.max_raise_to(self.human)
            self.raise_slider.minimum = low
            self.raise_slider.maximum = max(low, high)
            self._raise_amount = max(low, min(self._raise_amount, high))
            self.raise_slider.value = self._raise_amount

        idle = not self._hand_live
        self.next_button.visible = idle
        self.next_button.enabled = idle and self.bank.chips >= BIG_BLIND

    # ------------------------------------------------------------- layout --
    def _hole_positions(self, seat: int) -> List[Tuple[int, int]]:
        centre = self._seat_positions[seat]
        size = HOLE_SIZE if seat else BOARD_SIZE
        spread = size[0] + 8
        left = centre[0] - spread // 2 - size[0] // 2
        return [(left, centre[1] - size[1] // 2),
                (left + spread, centre[1] - size[1] // 2)]

    def _board_positions(self) -> List[Tuple[int, int]]:
        count = 5
        total = count * BOARD_SIZE[0] + (count - 1) * 12
        start = config.BASE_WIDTH // 2 - total // 2
        return [(start + index * (BOARD_SIZE[0] + 12), BOARD_Y) for index in range(count)]

    def _sync_flight(self) -> None:
        targets = []
        showdown = self.game.is_hand_over and self.game.result \
            and self.game.result.went_to_showdown
        for index, player in enumerate(self.players):
            if player.sitting_out or not player.hole:
                continue
            face_up = player.is_human or (showdown and not player.folded)
            for card_index, position in enumerate(self._hole_positions(player.seat)):
                targets.append(((player.seat, card_index), position, face_up))
        for index, position in enumerate(self._board_positions()[:len(self.game.board)]):
            targets.append((("board", index), position, True))
        self.flight.sync(targets)

    # --------------------------------------------------------------- draw --
    def draw_background(self, surface: pygame.Surface) -> None:
        render.gradient(surface, surface.get_rect(), (12, 58, 44), theme.BG_DEEP)
        table = pygame.Rect(0, 0, 900, 420)
        table.center = (config.BASE_WIDTH // 2, 300)
        pygame.draw.ellipse(surface, theme.darken(theme.WOOD, 0.2), table.inflate(36, 36))
        pygame.draw.ellipse(surface, theme.FELT, table)
        pygame.draw.ellipse(surface, theme.FELT_DARK, table, 4)
        render.vignette(surface, 150)

    def draw_content(self, surface: pygame.Surface) -> None:
        self._draw_pot(surface)
        self._draw_board(surface)
        for player in self.players:
            self._draw_seat(surface, player)
        self._draw_action_context(surface)
        if not self._hand_live and self._result_timer > 0:
            self._draw_result(surface)

    def _draw_pot(self, surface: pygame.Surface) -> None:
        pot = self.game.pot
        badge = pygame.Rect(0, 0, 196, 34)
        badge.center = (config.BASE_WIDTH // 2, 244)
        render.rounded_rect(surface, badge, theme.with_alpha(theme.BG_DEEP, 210), 17)
        render.rounded_rect(surface, badge, theme.GOLD_DIM, 17, width=1)
        chip = cardrender.chip_surface(100, 12)
        surface.blit(chip, chip.get_rect(center=(badge.x + 22, badge.centery)))
        render.text(surface, self.fonts.small(bold=True), f"POT  {pot:,}",
                    (badge.x + 42, badge.centery), theme.GOLD, anchor="midleft")

        pots = self.game.result.pots if self.game.result else []
        if len(pots) > 1:
            render.text(surface, self.fonts.tiny(),
                        "   ".join(f"{'main' if i == 0 else 'side'} {p.amount:,}"
                                  for i, p in enumerate(pots)),
                        (badge.centerx, badge.bottom + 4), theme.TEXT_DIM, anchor="midtop")

    def _draw_board(self, surface: pygame.Surface) -> None:
        winning = set()
        if self.game.is_hand_over and self.game.result and self.game.result.went_to_showdown:
            for entry in self.game.result.entries:
                if entry.player is self.human and entry.rank:
                    winning = {str(card) for card in entry.rank.cards}
        for index, card in enumerate(self.game.board):
            highlight = theme.GOLD if str(card) in winning else None
            self.flight.draw_card(surface, ("board", index), card, BOARD_SIZE,
                                  highlight=highlight)
        street = self.game.street.value.upper()
        left = self._board_positions()[0][0]
        render.text(surface, self.fonts.tiny(bold=True), street,
                    (left - 22, BOARD_Y + BOARD_SIZE[1] // 2),
                    theme.TEXT_MUTED, anchor="midright")

    def _draw_seat(self, surface: pygame.Surface, player: rules.Player) -> None:
        centre = self._seat_positions[player.seat]
        active = self.game.current_player is player and self._hand_live
        plate = pygame.Rect(0, 0, 210, 54)
        plate.center = (centre[0], centre[1] + (93 if player.seat == 0 else 76))

        if active:
            pulse = anim.pulse(self.time, 5, 0.4, 1.0)
            render.glow(surface, plate, theme.GOLD, radius=12, spread=14,
                        alpha=int(110 * pulse))
        edge = theme.GOLD if active else theme.PANEL_EDGE
        if player.folded and not player.sitting_out:
            edge = theme.darken(theme.PANEL_EDGE, 0.4)
        render.panel(surface, plate, theme.PANEL, edge, radius=12)

        name_colour = theme.TEXT if not player.folded else theme.TEXT_MUTED
        render.text(surface, self.fonts.small(bold=True), player.name,
                    (plate.x + 12, plate.y + 8), name_colour)
        render.text(surface, self.fonts.small(bold=True), f"{player.chips:,}",
                    (plate.right - 12, plate.y + 8), theme.GOLD, anchor="topright")
        if player.last_action:
            render.text(surface, self.fonts.tiny(), player.last_action,
                        (plate.x + 12, plate.y + 32), theme.TEXT_DIM)
        if player.profile:
            render.text(surface, self.fonts.tiny(), player.profile.name,
                        (plate.right - 12, plate.y + 32), theme.TEXT_MUTED,
                        anchor="topright")

        if self.game.button == self.players.index(player) and self._hand_live:
            marker = (plate.right - 4, plate.y - 4)
            render.circle(surface, marker, 12, theme.TEXT)
            render.text(surface, self.fonts.tiny(bold=True), "D", marker, theme.INK,
                        anchor="center")

        if player.hole and not player.sitting_out:
            size = HOLE_SIZE if player.seat else BOARD_SIZE
            for card_index, card in enumerate(player.hole):
                self.flight.draw_card(surface, (player.seat, card_index), card, size,
                                      dim=player.folded)

        if player.bet:
            chip_at = CHIP_ANCHORS[player.seat]
            cardrender.draw_chip_stack(surface, chip_at, config.CHIP_DENOMINATIONS[1],
                                       min(4, max(1, player.bet // 25)), radius=12, spacing=3)
            render.text(surface, self.fonts.tiny(bold=True), f"{player.bet:,}",
                        (chip_at[0] + 20, chip_at[1]), theme.GOLD, anchor="midleft")

    def _draw_action_context(self, surface: pygame.Surface) -> None:
        if not self._is_human_turn:
            return
        owed = self.game.to_call(self.human)
        pot = self.game.pot
        odds = owed / (pot + owed) if owed else 0.0
        box = pygame.Rect(40, 584, 292, 86)
        render.panel(surface, box, theme.with_alpha(theme.PANEL, 210), theme.PANEL_EDGE,
                     radius=10, alpha=220)
        render.text(surface, self.fonts.tiny(bold=True), "YOUR TURN",
                    (box.x + 14, box.y + 10), theme.GOLD)
        lines = [
            f"to call  {owed:,}",
            f"pot  {pot:,}",
            f"pot odds  {odds * 100:.0f}%" if owed else "no bet to you",
        ]
        for index, line in enumerate(lines):
            render.text(surface, self.fonts.tiny(), line,
                        (box.x + 14, box.y + 32 + index * 16), theme.TEXT_DIM)

    def _draw_result(self, surface: pygame.Surface) -> None:
        result = self.game.result
        if not result:
            return
        box = pygame.Rect(0, 0, 460, 96)
        box.center = (config.BASE_WIDTH // 2, 404)
        colour = theme.WIN if self.human.won_last else theme.LOSE
        render.panel(surface, box, theme.PANEL, colour, radius=14)
        headline = (
            f"You win {self.human.won_last:,}" if self.human.won_last
            else "Hand lost"
        )
        render.text(surface, self.fonts.large(bold=True), headline,
                    (box.centerx, box.y + 30), colour, anchor="center")
        if self.last_result_text:
            render.text(surface, self.fonts.small(), self.last_result_text,
                        (box.centerx, box.y + 64), theme.TEXT_DIM, anchor="center")
