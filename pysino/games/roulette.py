"""European (single zero) roulette.

Every inside and outside bet on the felt covers some set of numbers, and for a
37 pocket wheel the fair-looking payout is always ``36 / covered - 1`` to one.
Expressing bets that way means one formula handles straights, splits, corners,
dozens and the even-money bets, and the 2.70% house edge falls out of the zero
being on the wheel but never in a bet's coverage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Sequence, Tuple

#: Pocket order around a real European wheel, used to animate the ball.
WHEEL_ORDER: Tuple[int, ...] = (
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
)

RED_NUMBERS: FrozenSet[int] = frozenset(
    {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
)
BLACK_NUMBERS: FrozenSet[int] = frozenset(set(range(1, 37)) - RED_NUMBERS)


def pocket_index(number: int) -> int:
    """Position of ``number`` around the physical wheel."""
    return WHEEL_ORDER.index(number)


def pocket_angle(number: int, wheel_angle: float = 0.0) -> float:
    """Screen-space angle of a pocket once the wheel has turned.

    The wheel face is drawn with pocket ``i`` occupying ``[i*step, (i+1)*step]``
    and is then rotated by ``-wheel_angle``, which in screen coordinates (where
    y grows downward) advances every angle by ``+wheel_angle``.  The ball has to
    finish exactly here or it will settle on the wrong number.
    """
    step = math.tau / len(WHEEL_ORDER)
    return pocket_index(number) * step + step / 2 + wheel_angle


def colour_of(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in RED_NUMBERS else "black"


def payout_odds(covered: int) -> int:
    """``x`` in ``x:1`` for a bet covering ``covered`` numbers."""
    if not 1 <= covered <= 36 or 36 % covered:
        raise ValueError(f"no standard bet covers {covered} numbers")
    return 36 // covered - 1


@dataclass(frozen=True)
class Bet:
    """A wager on a set of numbers.  ``kind`` is purely descriptive."""

    kind: str
    numbers: FrozenSet[int]
    amount: int

    @property
    def odds(self) -> int:
        return payout_odds(len(self.numbers))

    def wins_on(self, number: int) -> bool:
        return number in self.numbers

    def payout(self, number: int) -> int:
        """Gross return: stake plus winnings, or zero."""
        if not self.wins_on(number):
            return 0
        return self.amount * (self.odds + 1)

    def label(self) -> str:
        return f"{self.kind} ({self.odds}:1)"


# --------------------------------------------------------------- bet makers --
def straight(number: int, amount: int) -> Bet:
    return Bet(f"Straight {number}", frozenset({number}), amount)


def split(a: int, b: int, amount: int) -> Bet:
    return Bet(f"Split {a}/{b}", frozenset({a, b}), amount)


def street(row_start: int, amount: int) -> Bet:
    numbers = frozenset({row_start, row_start + 1, row_start + 2})
    return Bet(f"Street {row_start}-{row_start + 2}", numbers, amount)


def corner(top_left: int, amount: int) -> Bet:
    numbers = frozenset({top_left, top_left + 1, top_left + 3, top_left + 4})
    return Bet(f"Corner {top_left}", numbers, amount)


def six_line(row_start: int, amount: int) -> Bet:
    numbers = frozenset(range(row_start, row_start + 6))
    return Bet(f"Six Line {row_start}-{row_start + 5}", numbers, amount)


def column(index: int, amount: int) -> Bet:
    """``index`` is 0, 1 or 2 for the three 12-number columns."""
    numbers = frozenset(n for n in range(1, 37) if (n - 1) % 3 == index)
    return Bet(f"Column {index + 1}", numbers, amount)


def dozen(index: int, amount: int) -> Bet:
    start = index * 12 + 1
    return Bet(f"{start}-{start + 11}", frozenset(range(start, start + 12)), amount)


def red(amount: int) -> Bet:
    return Bet("Red", RED_NUMBERS, amount)


def black(amount: int) -> Bet:
    return Bet("Black", BLACK_NUMBERS, amount)


def odd(amount: int) -> Bet:
    return Bet("Odd", frozenset(n for n in range(1, 37) if n % 2), amount)


def even(amount: int) -> Bet:
    return Bet("Even", frozenset(n for n in range(1, 37) if n % 2 == 0), amount)


def low(amount: int) -> Bet:
    return Bet("1-18", frozenset(range(1, 19)), amount)


def high(amount: int) -> Bet:
    return Bet("19-36", frozenset(range(19, 37)), amount)


@dataclass
class SpinResult:
    number: int
    colour: str
    total_staked: int
    total_returned: int
    winners: List[Bet]
    losers: List[Bet]

    @property
    def net(self) -> int:
        return self.total_returned - self.total_staked


class RouletteGame:
    def __init__(self, rng) -> None:
        self.rng = rng
        self.history: List[int] = []

    def spin(self) -> int:
        number = self.rng.choice(WHEEL_ORDER)
        self.history.append(number)
        if len(self.history) > 50:
            self.history.pop(0)
        return number

    def settle(self, bets: Sequence[Bet], number: int) -> SpinResult:
        winners = [bet for bet in bets if bet.wins_on(number)]
        losers = [bet for bet in bets if not bet.wins_on(number)]
        return SpinResult(
            number=number,
            colour=colour_of(number),
            total_staked=sum(bet.amount for bet in bets),
            total_returned=sum(bet.payout(number) for bet in winners),
            winners=winners,
            losers=losers,
        )

    def play(self, bets: Sequence[Bet]) -> SpinResult:
        return self.settle(bets, self.spin())


def hot_and_cold(history: Iterable[int], count: int = 3) -> Tuple[List[int], List[int]]:
    """Most and least frequent numbers in recent history, for the scoreboard."""
    tally: Dict[int, int] = {number: 0 for number in range(37)}
    for number in history:
        tally[number] += 1
    ordered = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    hot = [number for number, seen in ordered[:count] if seen]
    cold = [number for number, _ in ordered[::-1][:count]]
    return hot, cold
