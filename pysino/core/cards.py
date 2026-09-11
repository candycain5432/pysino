"""Playing cards, decks and dealing shoes.

Cards are immutable value objects with a compact integer rank so the poker
evaluator can work with plain arithmetic instead of string comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Sequence

#: Ranks run 2..14 so that Ace is naturally high; the evaluator special-cases
#: the wheel straight (A-2-3-4-5) where the ace plays low.
RANKS = tuple(range(2, 15))
SUITS = ("s", "h", "d", "c")

RANK_NAMES = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K", 14: "A",
}
RANK_VALUES = {name: value for value, name in RANK_NAMES.items()}

SUIT_NAMES = {"s": "Spades", "h": "Hearts", "d": "Diamonds", "c": "Clubs"}
SUIT_SYMBOLS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
RED_SUITS = frozenset({"h", "d"})


@dataclass(frozen=True, order=True)
class Card:
    """A single playing card.  ``rank`` is 2-14, ``suit`` is one of ``shdc``."""

    rank: int
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANK_NAMES:
            raise ValueError(f"bad rank: {self.rank!r}")
        if self.suit not in SUIT_NAMES:
            raise ValueError(f"bad suit: {self.suit!r}")

    @property
    def rank_name(self) -> str:
        return RANK_NAMES[self.rank]

    @property
    def symbol(self) -> str:
        return SUIT_SYMBOLS[self.suit]

    @property
    def is_red(self) -> bool:
        return self.suit in RED_SUITS

    @property
    def is_ace(self) -> bool:
        return self.rank == 14

    @property
    def blackjack_value(self) -> int:
        """Face cards count ten; an ace counts eleven until it has to shrink."""
        if self.rank >= 11:
            return 10 if self.rank < 14 else 11
        return self.rank

    def __str__(self) -> str:
        return f"{self.rank_name}{self.suit}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Card({self})"

    @classmethod
    def parse(cls, text: str) -> "Card":
        """Build a card from shorthand such as ``"As"``, ``"10h"`` or ``"Td"``."""
        text = text.strip()
        if len(text) < 2:
            raise ValueError(f"cannot parse card: {text!r}")
        rank_text, suit = text[:-1].upper(), text[-1].lower()
        if rank_text == "T":
            rank_text = "10"
        if rank_text not in RANK_VALUES:
            raise ValueError(f"cannot parse rank in {text!r}")
        return cls(RANK_VALUES[rank_text], suit)


def parse_hand(text: str) -> List[Card]:
    """Parse a whitespace separated hand, e.g. ``"As Kd 10h"``."""
    return [Card.parse(token) for token in text.split()]


def full_deck() -> List[Card]:
    """All 52 cards in a fixed, unshuffled order."""
    return [Card(rank, suit) for suit in SUITS for rank in RANKS]


class Deck:
    """A single shuffled deck that deals from the top."""

    def __init__(self, rng, cards: Sequence[Card] | None = None) -> None:
        self.rng = rng
        self._cards: List[Card] = list(cards) if cards is not None else full_deck()
        if cards is None:
            self.shuffle()

    def shuffle(self) -> None:
        self._cards = full_deck()
        self.rng.shuffle(self._cards)

    def draw(self) -> Card:
        if not self._cards:
            raise IndexError("deck is empty")
        return self._cards.pop()

    def deal(self, count: int) -> List[Card]:
        return [self.draw() for _ in range(count)]

    def remove(self, cards: Iterable[Card]) -> None:
        """Take specific cards out of the deck (used when seeding scenarios)."""
        for card in cards:
            self._cards.remove(card)

    def __len__(self) -> int:
        return len(self._cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self._cards)


class Shoe:
    """A multi-deck dealing shoe with a cut card, as used for blackjack.

    The shoe reports when it needs reshuffling rather than doing it mid-hand,
    so a hand that starts is always guaranteed enough cards to finish.
    """

    def __init__(self, rng, decks: int = 6, penetration: float = 0.75) -> None:
        if decks < 1:
            raise ValueError("a shoe needs at least one deck")
        if not 0.1 <= penetration <= 1.0:
            raise ValueError("penetration must be between 0.1 and 1.0")
        self.rng = rng
        self.decks = decks
        self.penetration = penetration
        self._cards: List[Card] = []
        self._dealt = 0
        self.shuffles = 0
        self.shuffle()

    def shuffle(self) -> None:
        self._cards = [card for _ in range(self.decks) for card in full_deck()]
        self.rng.shuffle(self._cards)
        self._dealt = 0
        self.shuffles += 1

    @property
    def total_cards(self) -> int:
        return 52 * self.decks

    @property
    def cards_remaining(self) -> int:
        return len(self._cards)

    @property
    def needs_shuffle(self) -> bool:
        """True once the cut card is reached."""
        return self._dealt >= self.total_cards * self.penetration

    def draw(self) -> Card:
        if not self._cards:
            # Safety net: a hand must never run dry, even with pathological
            # penetration settings or an unusual number of splits.
            self.shuffle()
        self._dealt += 1
        return self._cards.pop()

    def deal(self, count: int) -> List[Card]:
        return [self.draw() for _ in range(count)]

    def __len__(self) -> int:
        return len(self._cards)
