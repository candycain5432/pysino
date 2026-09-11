"""Poker hand evaluation for five to seven card hands.

The evaluator picks the best five card hand out of whatever it is given and
returns a :class:`HandRank`.  Ranks pack down to a single integer so the
hold'em bot can compare thousands of Monte Carlo rollouts cheaply, while the
``cards`` field keeps the actual winning five around for the UI to highlight.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .cards import Card, RANK_NAMES

HIGH_CARD = 0
PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    PAIR: "Pair",
    TWO_PAIR: "Two Pair",
    THREE_OF_A_KIND: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    FOUR_OF_A_KIND: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}

_PLURALS = {
    2: "Twos", 3: "Threes", 4: "Fours", 5: "Fives", 6: "Sixes", 7: "Sevens",
    8: "Eights", 9: "Nines", 10: "Tens", 11: "Jacks", 12: "Queens",
    13: "Kings", 14: "Aces",
}

#: Tiebreakers are packed base-15 (ranks only ever reach 14), five deep.
_PACK_BASE = 15
_PACK_WIDTH = 5


@dataclass(frozen=True)
class HandRank:
    """The strength of a made hand.  Larger compares as better."""

    category: int
    tiebreakers: Tuple[int, ...]
    cards: Tuple[Card, ...] = field(default=(), compare=False, repr=False)

    @property
    def value(self) -> int:
        """A single integer encoding category and kickers, for fast compares."""
        packed = self.category
        padded = tuple(self.tiebreakers) + (0,) * (_PACK_WIDTH - len(self.tiebreakers))
        for tiebreaker in padded[:_PACK_WIDTH]:
            packed = packed * _PACK_BASE + tiebreaker
        return packed

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES[self.category]

    def describe(self) -> str:
        """A human readable summary such as ``"Kings full of Sevens"``."""
        ranks = self.tiebreakers
        if self.category == STRAIGHT_FLUSH:
            if ranks[0] == 14:
                return "Royal Flush"
            return f"Straight Flush, {RANK_NAMES[ranks[0]]} high"
        if self.category == FOUR_OF_A_KIND:
            return f"Four {_PLURALS[ranks[0]]}"
        if self.category == FULL_HOUSE:
            return f"{_PLURALS[ranks[0]]} full of {_PLURALS[ranks[1]]}"
        if self.category == FLUSH:
            return f"Flush, {RANK_NAMES[ranks[0]]} high"
        if self.category == STRAIGHT:
            return f"Straight, {RANK_NAMES[ranks[0]]} high"
        if self.category == THREE_OF_A_KIND:
            return f"Three {_PLURALS[ranks[0]]}"
        if self.category == TWO_PAIR:
            return f"Two Pair, {_PLURALS[ranks[0]]} and {_PLURALS[ranks[1]]}"
        if self.category == PAIR:
            return f"Pair of {_PLURALS[ranks[0]]}"
        return f"{RANK_NAMES[ranks[0]]} high"

    # Ordering is by packed value; the winning cards deliberately do not count.
    def __lt__(self, other: "HandRank") -> bool:
        return self.value < other.value

    def __le__(self, other: "HandRank") -> bool:
        return self.value <= other.value

    def __gt__(self, other: "HandRank") -> bool:
        return self.value > other.value

    def __ge__(self, other: "HandRank") -> bool:
        return self.value >= other.value


def _straight_high(ranks: Sequence[int]) -> int:
    """Highest card of the best straight in ``ranks``, or 0 if there is none.

    Aces play low as well as high, so a wheel (A-2-3-4-5) reports a high of 5.
    """
    unique = set(ranks)
    if 14 in unique:
        unique.add(1)
    for high in range(14, 4, -1):
        if all(high - offset in unique for offset in range(5)):
            return high
    return 0


def _straight_cards(cards: Sequence[Card], high: int) -> Tuple[Card, ...]:
    """Pick one card per rank making up the straight ending at ``high``."""
    wanted = [high - offset for offset in range(5)]
    # In the wheel the ace is stored as rank 14 but plays as 1.
    wanted = [14 if rank == 1 else rank for rank in wanted]
    by_rank: Dict[int, Card] = {}
    for card in cards:
        by_rank.setdefault(card.rank, card)
    return tuple(by_rank[rank] for rank in wanted)


def evaluate(cards: Sequence[Card]) -> HandRank:
    """Evaluate the best five card hand available in ``cards`` (5-7 cards)."""
    cards = list(cards)
    if len(cards) < 5:
        raise ValueError("need at least five cards to evaluate a poker hand")

    rank_counts = Counter(card.rank for card in cards)
    suit_counts = Counter(card.suit for card in cards)

    flush_suit = next((suit for suit, n in suit_counts.items() if n >= 5), None)
    if flush_suit is not None:
        flush_cards = sorted(
            (card for card in cards if card.suit == flush_suit),
            key=lambda card: card.rank,
            reverse=True,
        )
        high = _straight_high([card.rank for card in flush_cards])
        if high:
            return HandRank(STRAIGHT_FLUSH, (high,), _straight_cards(flush_cards, high))

    # Sort ranks by how many times they appear, then by rank: this puts quads
    # and trips first and gives kickers in descending order for free.
    ordered = sorted(rank_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    shape = [count for _, count in ordered]

    def cards_of(rank: int, limit: int) -> List[Card]:
        return [card for card in cards if card.rank == rank][:limit]

    if shape[0] == 4:
        quad = ordered[0][0]
        kicker = max(rank for rank in rank_counts if rank != quad)
        return HandRank(
            FOUR_OF_A_KIND, (quad, kicker), tuple(cards_of(quad, 4) + cards_of(kicker, 1))
        )

    if shape[0] == 3 and len(shape) > 1 and shape[1] >= 2:
        trips = ordered[0][0]
        pair = max(rank for rank, count in ordered[1:] if count >= 2)
        return HandRank(
            FULL_HOUSE, (trips, pair), tuple(cards_of(trips, 3) + cards_of(pair, 2))
        )

    if flush_suit is not None:
        best = flush_cards[:5]
        return HandRank(FLUSH, tuple(card.rank for card in best), tuple(best))

    high = _straight_high(list(rank_counts))
    if high:
        return HandRank(STRAIGHT, (high,), _straight_cards(cards, high))

    if shape[0] == 3:
        trips = ordered[0][0]
        kickers = sorted((rank for rank in rank_counts if rank != trips), reverse=True)[:2]
        picked = cards_of(trips, 3) + [cards_of(rank, 1)[0] for rank in kickers]
        return HandRank(THREE_OF_A_KIND, (trips, *kickers), tuple(picked))

    pairs = sorted((rank for rank, count in rank_counts.items() if count == 2), reverse=True)
    if len(pairs) >= 2:
        high_pair, low_pair = pairs[0], pairs[1]
        kicker = max(rank for rank in rank_counts if rank not in (high_pair, low_pair))
        picked = cards_of(high_pair, 2) + cards_of(low_pair, 2) + cards_of(kicker, 1)
        return HandRank(TWO_PAIR, (high_pair, low_pair, kicker), tuple(picked))

    if pairs:
        pair = pairs[0]
        kickers = sorted((rank for rank in rank_counts if rank != pair), reverse=True)[:3]
        picked = cards_of(pair, 2) + [cards_of(rank, 1)[0] for rank in kickers]
        return HandRank(PAIR, (pair, *kickers), tuple(picked))

    best = sorted(cards, key=lambda card: card.rank, reverse=True)[:5]
    return HandRank(HIGH_CARD, tuple(card.rank for card in best), tuple(best))


def compare(left: Sequence[Card], right: Sequence[Card]) -> int:
    """``1`` if ``left`` wins, ``-1`` if ``right`` wins, ``0`` on a split."""
    a, b = evaluate(left).value, evaluate(right).value
    return (a > b) - (a < b)
