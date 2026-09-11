"""Blackjack: multi-deck shoe, splits, doubles, insurance and late surrender.

House rules follow a common Vegas shoe game: 6 decks, dealer stands on soft 17,
blackjack pays 3:2, double on any two cards, double after split, split up to
four hands, aces split once and receive a single card each.  The knobs live in
:class:`Rules` so a scene (or a test) can change them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from ..core.cards import Card, Shoe


class Action(str, Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"


class State(str, Enum):
    BETTING = "betting"
    INSURANCE = "insurance"
    PLAYER = "player"
    DEALER = "dealer"
    DONE = "done"


class Outcome(str, Enum):
    BLACKJACK = "blackjack"
    WIN = "win"
    PUSH = "push"
    LOSE = "lose"
    BUST = "bust"
    SURRENDER = "surrender"


@dataclass
class Rules:
    decks: int = 6
    penetration: float = 0.75
    dealer_hits_soft_17: bool = False
    blackjack_payout: float = 1.5
    max_hands: int = 4
    double_after_split: bool = True
    allow_surrender: bool = True
    #: Split aces draw exactly one card each and may not be re-split.
    one_card_after_split_aces: bool = True


def hand_value(cards: Sequence[Card]) -> Tuple[int, bool]:
    """Return ``(total, is_soft)``; aces drop from 11 to 1 as needed."""
    total = sum(card.blackjack_value for card in cards)
    aces = sum(1 for card in cards if card.is_ace)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0 and total <= 21


@dataclass
class Hand:
    """One betting box.  A split turns one hand into two."""

    cards: List[Card] = field(default_factory=list)
    bet: int = 0
    doubled: bool = False
    from_split: bool = False
    split_aces: bool = False
    stood: bool = False
    surrendered: bool = False
    outcome: Optional[Outcome] = None
    payout: int = 0

    @property
    def total(self) -> int:
        return hand_value(self.cards)[0]

    @property
    def is_soft(self) -> bool:
        return hand_value(self.cards)[1]

    @property
    def is_busted(self) -> bool:
        return self.total > 21

    @property
    def is_blackjack(self) -> bool:
        """Two-card 21, which a split hand can never be."""
        return len(self.cards) == 2 and self.total == 21 and not self.from_split

    @property
    def is_charlie(self) -> bool:
        """Five cards without busting - cosmetic here, but worth a badge."""
        return len(self.cards) >= 5 and not self.is_busted

    @property
    def is_finished(self) -> bool:
        return self.stood or self.surrendered or self.is_busted or self.total == 21

    @property
    def can_split(self) -> bool:
        return (
            len(self.cards) == 2
            and self.cards[0].blackjack_value == self.cards[1].blackjack_value
            and not self.split_aces
        )

    def label(self) -> str:
        total, soft = hand_value(self.cards)
        if self.is_blackjack:
            return "Blackjack"
        if total > 21:
            return f"Bust ({total})"
        if soft and total != 21:
            return f"{total - 10}/{total}"
        return str(total)


@dataclass
class RoundResult:
    hands: List[Hand]
    dealer_cards: List[Card]
    staked: int
    returned: int
    insurance_bet: int = 0
    insurance_payout: int = 0

    @property
    def net(self) -> int:
        return self.returned - self.staked


class BlackjackGame:
    """A single seat at a blackjack table.

    The game never touches the player's chips; it reports what each hand costs
    and pays, and the scene moves chips in and out of the bank.
    """

    def __init__(self, rng, rules: Rules | None = None) -> None:
        self.rules = rules or Rules()
        self.shoe = Shoe(rng, self.rules.decks, self.rules.penetration)
        self.state = State.BETTING
        self.hands: List[Hand] = []
        self.dealer_cards: List[Card] = []
        self.active_index = 0
        self.insurance_bet = 0
        self.insurance_payout = 0
        self.result: Optional[RoundResult] = None
        self.hole_hidden = True

    # ------------------------------------------------------------ helpers --
    @property
    def active_hand(self) -> Optional[Hand]:
        if self.state is not State.PLAYER or self.active_index >= len(self.hands):
            return None
        return self.hands[self.active_index]

    @property
    def dealer_upcard(self) -> Optional[Card]:
        return self.dealer_cards[0] if self.dealer_cards else None

    @property
    def dealer_total(self) -> int:
        return hand_value(self.dealer_cards)[0]

    @property
    def dealer_has_blackjack(self) -> bool:
        return len(self.dealer_cards) == 2 and self.dealer_total == 21

    @property
    def total_staked(self) -> int:
        return sum(hand.bet for hand in self.hands) + self.insurance_bet

    # ------------------------------------------------------------- betting --
    def start_round(self, bet: int) -> None:
        """Deal a new hand.  ``bet`` chips must already have left the bank."""
        if self.state not in (State.BETTING, State.DONE):
            raise RuntimeError(f"cannot deal from state {self.state}")
        if bet <= 0:
            raise ValueError("bet must be positive")
        if self.shoe.needs_shuffle:
            self.shoe.shuffle()

        self.hands = [Hand(bet=bet)]
        self.dealer_cards = []
        self.active_index = 0
        self.insurance_bet = 0
        self.insurance_payout = 0
        self.result = None
        self.hole_hidden = True

        for _ in range(2):
            self.hands[0].cards.append(self.shoe.draw())
            self.dealer_cards.append(self.shoe.draw())

        if self.dealer_upcard and self.dealer_upcard.is_ace:
            self.state = State.INSURANCE
        else:
            self._peek_for_naturals()

    # ---------------------------------------------------------- insurance --
    @property
    def insurance_cost(self) -> int:
        return self.hands[0].bet // 2 if self.hands else 0

    def take_insurance(self) -> int:
        """Buy insurance for half the original bet; returns the cost."""
        if self.state is not State.INSURANCE:
            raise RuntimeError("insurance is not on offer")
        self.insurance_bet = self.insurance_cost
        self._resolve_insurance()
        return self.insurance_bet

    def decline_insurance(self) -> None:
        if self.state is not State.INSURANCE:
            raise RuntimeError("insurance is not on offer")
        self.insurance_bet = 0
        self._resolve_insurance()

    def _resolve_insurance(self) -> None:
        # Insurance pays 2:1, so a winning bet returns three times the stake.
        if self.insurance_bet and self.dealer_has_blackjack:
            self.insurance_payout = self.insurance_bet * 3
        self._peek_for_naturals()

    def _peek_for_naturals(self) -> None:
        """The dealer checks the hole card; a natural ends the round at once."""
        if self.dealer_has_blackjack or self.hands[0].is_blackjack:
            self.hole_hidden = False
            self._settle()
        else:
            self.state = State.PLAYER

    # ------------------------------------------------------- player action --
    def available_actions(self) -> List[Action]:
        hand = self.active_hand
        if hand is None:
            return []
        actions = [Action.HIT, Action.STAND]
        first_decision = len(hand.cards) == 2
        if first_decision and (self.rules.double_after_split or not hand.from_split):
            actions.append(Action.DOUBLE)
        if (
            hand.can_split
            and len(self.hands) < self.rules.max_hands
        ):
            actions.append(Action.SPLIT)
        if (
            self.rules.allow_surrender
            and first_decision
            and not hand.from_split
            and len(self.hands) == 1
        ):
            actions.append(Action.SURRENDER)
        return actions

    def _require(self, action: Action) -> Hand:
        if self.state is not State.PLAYER:
            raise RuntimeError(f"cannot act in state {self.state}")
        if action not in self.available_actions():
            raise RuntimeError(f"{action.value} is not available right now")
        hand = self.active_hand
        assert hand is not None
        return hand

    def hit(self) -> Card:
        hand = self._require(Action.HIT)
        card = self.shoe.draw()
        hand.cards.append(card)
        if hand.is_finished:
            self._advance()
        return card

    def stand(self) -> None:
        hand = self._require(Action.STAND)
        hand.stood = True
        self._advance()

    def double(self) -> Tuple[int, Card]:
        """Double the wager and take exactly one more card."""
        hand = self._require(Action.DOUBLE)
        extra = hand.bet
        hand.bet += extra
        hand.doubled = True
        card = self.shoe.draw()
        hand.cards.append(card)
        hand.stood = True
        self._advance()
        return extra, card

    def split(self) -> int:
        """Split the active hand, returning the extra chips it costs."""
        hand = self._require(Action.SPLIT)
        moved = hand.cards.pop()
        was_aces = moved.is_ace
        new_hand = Hand(
            cards=[moved],
            bet=hand.bet,
            from_split=True,
            split_aces=was_aces and self.rules.one_card_after_split_aces,
        )
        hand.from_split = True
        hand.split_aces = new_hand.split_aces
        self.hands.insert(self.active_index + 1, new_hand)

        hand.cards.append(self.shoe.draw())
        new_hand.cards.append(self.shoe.draw())

        if hand.split_aces:
            # Split aces get one card each and are done immediately.
            hand.stood = True
            new_hand.stood = True
            self._advance()
        elif hand.is_finished:
            self._advance()
        return new_hand.bet

    def surrender(self) -> None:
        hand = self._require(Action.SURRENDER)
        hand.surrendered = True
        self._advance()

    def _advance(self) -> None:
        """Move to the next unfinished hand, or hand play over to the dealer."""
        while self.active_index < len(self.hands):
            if not self.hands[self.active_index].is_finished:
                return
            self.active_index += 1
        self._play_dealer()

    # ------------------------------------------------------- dealer & pay --
    @property
    def dealer_must_draw(self) -> bool:
        total, soft = hand_value(self.dealer_cards)
        if total < 17:
            return True
        return total == 17 and soft and self.rules.dealer_hits_soft_17

    def _play_dealer(self) -> None:
        self.state = State.DEALER
        self.hole_hidden = False
        live = [h for h in self.hands if not h.is_busted and not h.surrendered]
        if live:
            while self.dealer_must_draw:
                self.dealer_cards.append(self.shoe.draw())
        self._settle()

    def _settle(self) -> None:
        dealer_total = self.dealer_total
        dealer_bj = self.dealer_has_blackjack
        dealer_bust = dealer_total > 21
        returned = 0

        for hand in self.hands:
            if hand.surrendered:
                hand.outcome = Outcome.SURRENDER
                hand.payout = hand.bet // 2
            elif hand.is_busted:
                hand.outcome = Outcome.BUST
                hand.payout = 0
            elif hand.is_blackjack and not dealer_bj:
                hand.outcome = Outcome.BLACKJACK
                hand.payout = hand.bet + int(hand.bet * self.rules.blackjack_payout)
            elif dealer_bj and not hand.is_blackjack:
                hand.outcome = Outcome.LOSE
                hand.payout = 0
            elif dealer_bj and hand.is_blackjack:
                hand.outcome = Outcome.PUSH
                hand.payout = hand.bet
            elif dealer_bust or hand.total > dealer_total:
                hand.outcome = Outcome.WIN
                hand.payout = hand.bet * 2
            elif hand.total < dealer_total:
                hand.outcome = Outcome.LOSE
                hand.payout = 0
            else:
                hand.outcome = Outcome.PUSH
                hand.payout = hand.bet
            returned += hand.payout

        returned += self.insurance_payout
        self.state = State.DONE
        self.result = RoundResult(
            hands=list(self.hands),
            dealer_cards=list(self.dealer_cards),
            staked=self.total_staked,
            returned=returned,
            insurance_bet=self.insurance_bet,
            insurance_payout=self.insurance_payout,
        )


def basic_strategy(hand: Hand, dealer_up: Card, actions: Sequence[Action]) -> Action:
    """Textbook basic strategy, used by the in-game hint button.

    Restricted to the actions actually on offer, so the advice is always legal.
    """
    total, soft = hand_value(hand.cards)
    up = dealer_up.blackjack_value
    up = 11 if dealer_up.is_ace else up

    def pick(*preferences: Action) -> Action:
        for choice in preferences:
            if choice in actions:
                return choice
        return Action.STAND if Action.STAND in actions else Action.HIT

    if hand.can_split and Action.SPLIT in actions:
        rank = hand.cards[0].blackjack_value
        if dealer_up.is_ace and hand.cards[0].is_ace:
            return Action.SPLIT
        if hand.cards[0].is_ace or rank == 8:
            return Action.SPLIT
        if rank in (2, 3, 7) and up <= 7:
            return Action.SPLIT
        if rank == 6 and up <= 6:
            return Action.SPLIT
        if rank == 9 and up in (2, 3, 4, 5, 6, 8, 9):
            return Action.SPLIT
        if rank == 4 and up in (5, 6):
            return Action.SPLIT

    if Action.SURRENDER in actions and not soft:
        if total == 16 and up in (9, 10, 11):
            return Action.SURRENDER
        if total == 15 and up == 10:
            return Action.SURRENDER

    if soft:
        if total >= 19:
            return pick(Action.STAND)
        if total == 18:
            if up in (3, 4, 5, 6):
                return pick(Action.DOUBLE, Action.STAND)
            if up in (2, 7, 8):
                return pick(Action.STAND)
            return pick(Action.HIT)
        if total == 17 and up in (3, 4, 5, 6):
            return pick(Action.DOUBLE, Action.HIT)
        if total in (15, 16) and up in (4, 5, 6):
            return pick(Action.DOUBLE, Action.HIT)
        if total in (13, 14) and up in (5, 6):
            return pick(Action.DOUBLE, Action.HIT)
        return pick(Action.HIT)

    if total >= 17:
        return pick(Action.STAND)
    if 13 <= total <= 16:
        return pick(Action.STAND) if up <= 6 else pick(Action.HIT)
    if total == 12:
        return pick(Action.STAND) if up in (4, 5, 6) else pick(Action.HIT)
    if total == 11:
        return pick(Action.DOUBLE, Action.HIT)
    if total == 10:
        return pick(Action.DOUBLE, Action.HIT) if up <= 9 else pick(Action.HIT)
    if total == 9:
        return pick(Action.DOUBLE, Action.HIT) if up in (3, 4, 5, 6) else pick(Action.HIT)
    return pick(Action.HIT)
