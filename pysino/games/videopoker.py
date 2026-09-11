"""Jacks or Better video poker on the classic 9/6 paytable.

Nine for a full house and six for a flush is the full-pay schedule, worth about
99.5% to a perfect player, which makes this comfortably the best value machine
on the Pysino floor.  Five cards are dealt, the player holds any subset, and
the rest are replaced from the same deck.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

from ..core import poker
from ..core.cards import Card, Deck, full_deck

MAX_COINS = 5

ROYAL_FLUSH = "royal_flush"
STRAIGHT_FLUSH = "straight_flush"
FOUR_OF_A_KIND = "four_of_a_kind"
FULL_HOUSE = "full_house"
FLUSH = "flush"
STRAIGHT = "straight"
THREE_OF_A_KIND = "three_of_a_kind"
TWO_PAIR = "two_pair"
JACKS_OR_BETTER = "jacks_or_better"

HAND_NAMES = {
    ROYAL_FLUSH: "Royal Flush",
    STRAIGHT_FLUSH: "Straight Flush",
    FOUR_OF_A_KIND: "Four of a Kind",
    FULL_HOUSE: "Full House",
    FLUSH: "Flush",
    STRAIGHT: "Straight",
    THREE_OF_A_KIND: "Three of a Kind",
    TWO_PAIR: "Two Pair",
    JACKS_OR_BETTER: "Jacks or Better",
}

#: Payout per coin wagered, indexed by coins played (1-5).  The royal flush
#: jumps from 250 to 800 per coin at five coins, which is the entire reason to
#: always bet max.
PAYTABLE: Dict[str, Tuple[int, ...]] = {
    ROYAL_FLUSH: (250, 500, 750, 1000, 4000),
    STRAIGHT_FLUSH: (50, 100, 150, 200, 250),
    FOUR_OF_A_KIND: (25, 50, 75, 100, 125),
    FULL_HOUSE: (9, 18, 27, 36, 45),
    FLUSH: (6, 12, 18, 24, 30),
    STRAIGHT: (4, 8, 12, 16, 20),
    THREE_OF_A_KIND: (3, 6, 9, 12, 15),
    TWO_PAIR: (2, 4, 6, 8, 10),
    JACKS_OR_BETTER: (1, 2, 3, 4, 5),
}

#: Display order, best first.
PAY_ORDER = (
    ROYAL_FLUSH, STRAIGHT_FLUSH, FOUR_OF_A_KIND, FULL_HOUSE, FLUSH,
    STRAIGHT, THREE_OF_A_KIND, TWO_PAIR, JACKS_OR_BETTER,
)


class State(str, Enum):
    IDLE = "idle"
    HOLDING = "holding"
    COMPLETE = "complete"


def classify(cards: Sequence[Card]) -> Optional[str]:
    """Name the paying hand, or ``None`` when it misses entirely."""
    if len(cards) != 5:
        raise ValueError("video poker hands are exactly five cards")
    rank = poker.evaluate(cards)
    category = rank.category
    if category == poker.STRAIGHT_FLUSH:
        return ROYAL_FLUSH if rank.tiebreakers[0] == 14 else STRAIGHT_FLUSH
    if category == poker.FOUR_OF_A_KIND:
        return FOUR_OF_A_KIND
    if category == poker.FULL_HOUSE:
        return FULL_HOUSE
    if category == poker.FLUSH:
        return FLUSH
    if category == poker.STRAIGHT:
        return STRAIGHT
    if category == poker.THREE_OF_A_KIND:
        return THREE_OF_A_KIND
    if category == poker.TWO_PAIR:
        return TWO_PAIR
    if category == poker.PAIR and rank.tiebreakers[0] >= 11:
        return JACKS_OR_BETTER
    return None


def payout_for(hand: Optional[str], coins: int, coin_value: int) -> int:
    """Chips returned for a finished hand."""
    if hand is None:
        return 0
    coins = max(1, min(MAX_COINS, coins))
    return PAYTABLE[hand][coins - 1] * coin_value


@dataclass
class VideoPokerGame:
    rng: object
    state: State = State.IDLE
    cards: List[Card] = field(default_factory=list)
    held: List[bool] = field(default_factory=lambda: [False] * 5)
    coins: int = MAX_COINS
    coin_value: int = 10
    drawn: List[int] = field(default_factory=list)
    result: Optional[str] = None
    payout: int = 0
    _deck: Optional[Deck] = None

    @property
    def bet(self) -> int:
        return self.coins * self.coin_value

    def deal(self, coins: int, coin_value: int) -> List[Card]:
        """Start a hand.  ``coins * coin_value`` chips must already be staked."""
        if not 1 <= coins <= MAX_COINS:
            raise ValueError(f"coins must be 1-{MAX_COINS}")
        if coin_value <= 0:
            raise ValueError("coin value must be positive")
        self.coins = coins
        self.coin_value = coin_value
        self._deck = Deck(self.rng)
        self.cards = self._deck.deal(5)
        self.held = [False] * 5
        self.drawn = []
        self.result = None
        self.payout = 0
        self.state = State.HOLDING
        return list(self.cards)

    def toggle_hold(self, index: int) -> bool:
        if self.state is not State.HOLDING:
            raise RuntimeError("no hand to hold")
        if not 0 <= index < 5:
            raise ValueError("card index out of range")
        self.held[index] = not self.held[index]
        return self.held[index]

    def set_holds(self, mask: Sequence[bool]) -> None:
        if len(mask) != 5:
            raise ValueError("hold mask must cover five cards")
        self.held = [bool(value) for value in mask]

    def draw(self) -> int:
        """Replace every unheld card and settle; returns the gross payout."""
        if self.state is not State.HOLDING:
            raise RuntimeError("nothing to draw")
        assert self._deck is not None
        self.drawn = [index for index, keep in enumerate(self.held) if not keep]
        for index in self.drawn:
            self.cards[index] = self._deck.draw()
        self.result = classify(self.cards)
        self.payout = payout_for(self.result, self.coins, self.coin_value)
        self.state = State.COMPLETE
        return self.payout


# --------------------------------------------------------------- the hint --
#: Above this many possible draws we sample instead of enumerating.
_EXACT_LIMIT = 2_000


def _hold_ev(held: Sequence[Card], remaining: Sequence[Card], draws: int,
             rng, samples: int) -> float:
    """Expected payout (in coins per coin bet) for keeping ``held``."""
    if draws == 0:
        hand = classify(held)
        return PAYTABLE[hand][0] if hand else 0.0

    total = 0.0
    count = 0
    possible = len(list(combinations(range(len(remaining)), draws))) if draws <= 2 else _EXACT_LIMIT + 1
    if possible <= _EXACT_LIMIT:
        for extra in combinations(remaining, draws):
            hand = classify(list(held) + list(extra))
            total += PAYTABLE[hand][0] if hand else 0.0
            count += 1
    else:
        for _ in range(samples):
            extra = rng.sample(list(remaining), draws)
            hand = classify(list(held) + extra)
            total += PAYTABLE[hand][0] if hand else 0.0
            count += 1
    return total / count if count else 0.0


def best_hold(cards: Sequence[Card], rng, samples: int = 600) -> Tuple[bool, ...]:
    """Suggest which cards to keep.

    Every one of the 32 hold patterns is scored.  Keeping three or more cards
    leaves few enough draws to enumerate exactly; the wider patterns are
    sampled, which is plenty accurate for a hint button.
    """
    if len(cards) != 5:
        raise ValueError("need a five card hand")
    remaining = [card for card in full_deck() if card not in cards]

    best_mask: Tuple[bool, ...] = (False,) * 5
    best_value = -1.0
    for pattern in range(32):
        mask = tuple(bool(pattern & (1 << index)) for index in range(5))
        held = [card for card, keep in zip(cards, mask) if keep]
        value = _hold_ev(held, remaining, 5 - len(held), rng, samples)
        if value > best_value:
            best_mask, best_value = mask, value
    return best_mask
