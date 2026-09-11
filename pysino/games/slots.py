"""A five reel, three row, twenty payline video slot.

Each reel has its own weighted symbol strip.  Lines pay left to right from reel
one, wilds substitute for everything except scatters, and three or more
scatters anywhere on the screen buy a round of free spins at a multiplier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

ROWS = 3
REELS = 5

CHERRY = "cherry"
LEMON = "lemon"
BELL = "bell"
HORSESHOE = "horseshoe"
DIAMOND = "diamond"
CROWN = "crown"
SEVEN = "seven"
WILD = "wild"
SCATTER = "scatter"

SYMBOLS = (CHERRY, LEMON, BELL, HORSESHOE, DIAMOND, CROWN, SEVEN, WILD, SCATTER)

#: Display glyphs; the renderer draws these with the emoji-free symbol font.
SYMBOL_GLYPHS = {
    CHERRY: "❀",
    LEMON: "◆",
    BELL: "♛",
    HORSESHOE: "∩",
    DIAMOND: "♦",
    CROWN: "♗",
    SEVEN: "7",
    WILD: "W",
    SCATTER: "★",
}

SYMBOL_NAMES = {
    CHERRY: "Cherry", LEMON: "Lemon", BELL: "Bell", HORSESHOE: "Horseshoe",
    DIAMOND: "Diamond", CROWN: "Crown", SEVEN: "Lucky 7", WILD: "Wild",
    SCATTER: "Scatter",
}

#: Payout as a multiple of the *line* bet for 3, 4 and 5 of a kind.  These
#: numbers and the reel weights below were tuned together against a simulated
#: 200k spin sample to land the machine at roughly 95% return to player.
PAYTABLE: Dict[str, Tuple[int, int, int]] = {
    CHERRY: (5, 20, 60),
    LEMON: (5, 20, 60),
    BELL: (10, 40, 125),
    HORSESHOE: (12, 50, 175),
    DIAMOND: (20, 75, 300),
    CROWN: (30, 125, 600),
    SEVEN: (60, 300, 1500),
    WILD: (125, 750, 5000),
}

#: Scatters pay a multiple of the *total* bet and ignore paylines entirely.
SCATTER_PAYS: Dict[int, int] = {3: 4, 4: 20, 5: 150}
FREE_SPIN_AWARD: Dict[int, int] = {3: 10, 4: 15, 5: 25}
FREE_SPIN_MULTIPLIER = 2

#: Row index touched on each of the five reels, for all twenty lines.
PAYLINES: Tuple[Tuple[int, ...], ...] = (
    (1, 1, 1, 1, 1), (0, 0, 0, 0, 0), (2, 2, 2, 2, 2), (0, 1, 2, 1, 0),
    (2, 1, 0, 1, 2), (0, 0, 1, 2, 2), (2, 2, 1, 0, 0), (1, 0, 0, 0, 1),
    (1, 2, 2, 2, 1), (0, 1, 1, 1, 0), (2, 1, 1, 1, 2), (1, 0, 1, 2, 1),
    (1, 2, 1, 0, 1), (0, 0, 1, 0, 0), (2, 2, 1, 2, 2), (1, 1, 0, 1, 1),
    (1, 1, 2, 1, 1), (0, 1, 0, 1, 0), (2, 1, 2, 1, 2), (0, 2, 0, 2, 0),
)
LINE_COUNT = len(PAYLINES)

#: Per-reel symbol weights.  The outer reels are stingier with high symbols,
#: which is what keeps five-of-a-kind rare without flattening the whole game.
REEL_WEIGHTS: Tuple[Dict[str, int], ...] = (
    {CHERRY: 32, LEMON: 32, BELL: 24, HORSESHOE: 20, DIAMOND: 16, CROWN: 12, SEVEN: 8, WILD: 4, SCATTER: 5},
    {CHERRY: 28, LEMON: 28, BELL: 24, HORSESHOE: 20, DIAMOND: 16, CROWN: 12, SEVEN: 8, WILD: 6, SCATTER: 5},
    {CHERRY: 28, LEMON: 28, BELL: 24, HORSESHOE: 20, DIAMOND: 16, CROWN: 12, SEVEN: 8, WILD: 6, SCATTER: 5},
    {CHERRY: 28, LEMON: 28, BELL: 24, HORSESHOE: 20, DIAMOND: 16, CROWN: 12, SEVEN: 8, WILD: 6, SCATTER: 5},
    {CHERRY: 36, LEMON: 36, BELL: 26, HORSESHOE: 22, DIAMOND: 16, CROWN: 12, SEVEN: 8, WILD: 4, SCATTER: 5},
)


def build_strip(weights: Dict[str, int]) -> List[str]:
    """Expand a weight table into a physical reel strip.

    The copies of each symbol are spread as evenly as the weights allow rather
    than laid down in blocks.  That matters more than it looks: a reel shows
    three consecutive strip positions at once, so a blocked strip would show
    three of the same symbol nearly every spin.
    """
    placed: Dict[str, int] = {symbol: 0 for symbol in weights}
    strip: List[str] = []
    for _ in range(sum(weights.values())):
        # Always extend with whichever symbol is furthest behind its share.
        symbol = min(
            (s for s in weights if placed[s] < weights[s]),
            key=lambda s: ((placed[s] + 0.5) / weights[s], s),
        )
        strip.append(symbol)
        placed[symbol] += 1
    return strip


REEL_STRIPS: Tuple[List[str], ...] = tuple(build_strip(w) for w in REEL_WEIGHTS)


@dataclass
class LineWin:
    line_index: int
    symbol: str
    count: int
    amount: int

    @property
    def positions(self) -> List[Tuple[int, int]]:
        """``(column, row)`` cells that made the win, for highlighting."""
        pattern = PAYLINES[self.line_index]
        return [(column, pattern[column]) for column in range(self.count)]


@dataclass
class SpinResult:
    grid: List[List[str]]
    line_bet: int
    total_bet: int
    line_wins: List[LineWin] = field(default_factory=list)
    scatter_count: int = 0
    scatter_win: int = 0
    free_spins_awarded: int = 0
    multiplier: int = 1
    was_free_spin: bool = False

    @property
    def base_win(self) -> int:
        return sum(win.amount for win in self.line_wins) + self.scatter_win

    @property
    def total_win(self) -> int:
        return self.base_win * self.multiplier

    @property
    def scatter_positions(self) -> List[Tuple[int, int]]:
        return [
            (column, row)
            for column in range(REELS)
            for row in range(ROWS)
            if self.grid[row][column] == SCATTER
        ]


def spin_grid(rng) -> List[List[str]]:
    """Stop each reel independently; returns ``grid[row][column]``."""
    columns = []
    for strip in REEL_STRIPS:
        stop = rng.randrange(len(strip))
        columns.append([strip[(stop + offset) % len(strip)] for offset in range(ROWS)])
    return [[columns[column][row] for column in range(REELS)] for row in range(ROWS)]


def evaluate_line(symbols: Sequence[str], line_bet: int) -> Optional[Tuple[str, int, int]]:
    """Score one payline, returning ``(symbol, count, amount)`` or ``None``.

    A run must start on reel one.  Wilds stand in for any paying symbol, and a
    leading run of pure wilds is paid at whichever rate is worth more.
    """
    best: Optional[Tuple[str, int, int]] = None

    leading_wilds = 0
    for symbol in symbols:
        if symbol != WILD:
            break
        leading_wilds += 1
    if leading_wilds >= 3:
        amount = PAYTABLE[WILD][leading_wilds - 3] * line_bet
        best = (WILD, leading_wilds, amount)

    base = next((s for s in symbols if s not in (WILD, SCATTER)), None)
    if base is not None:
        run = 0
        for symbol in symbols:
            if symbol == base or symbol == WILD:
                run += 1
            else:
                break
        if run >= 3:
            amount = PAYTABLE[base][run - 3] * line_bet
            if best is None or amount > best[2]:
                best = (base, run, amount)
    return best


def evaluate(grid: Sequence[Sequence[str]], line_bet: int, multiplier: int = 1,
             was_free_spin: bool = False) -> SpinResult:
    """Score a whole screen: every payline plus scatters."""
    total_bet = line_bet * LINE_COUNT
    result = SpinResult(
        grid=[list(row) for row in grid],
        line_bet=line_bet,
        total_bet=0 if was_free_spin else total_bet,
        multiplier=multiplier,
        was_free_spin=was_free_spin,
    )

    for index, pattern in enumerate(PAYLINES):
        symbols = [grid[pattern[column]][column] for column in range(REELS)]
        scored = evaluate_line(symbols, line_bet)
        if scored:
            symbol, count, amount = scored
            result.line_wins.append(LineWin(index, symbol, count, amount))

    scatters = sum(row.count(SCATTER) for row in grid)
    result.scatter_count = scatters
    if scatters >= 3:
        result.scatter_win = SCATTER_PAYS[min(scatters, 5)] * total_bet
        result.free_spins_awarded = FREE_SPIN_AWARD[min(scatters, 5)]
    return result


class SlotMachine:
    """Tracks free spin state between spins."""

    def __init__(self, rng) -> None:
        self.rng = rng
        self.free_spins = 0
        self.free_spin_winnings = 0
        self.last: Optional[SpinResult] = None

    @property
    def in_free_spins(self) -> bool:
        return self.free_spins > 0

    def spin(self, line_bet: int) -> SpinResult:
        """Spin once.  Free spins are consumed first and cost nothing."""
        if line_bet <= 0:
            raise ValueError("line bet must be positive")
        free = self.in_free_spins
        if free:
            self.free_spins -= 1
        grid = spin_grid(self.rng)
        result = evaluate(
            grid,
            line_bet,
            multiplier=FREE_SPIN_MULTIPLIER if free else 1,
            was_free_spin=free,
        )
        if result.free_spins_awarded:
            # Scatters landing during a bonus retrigger it.
            self.free_spins += result.free_spins_awarded
        if free:
            self.free_spin_winnings += result.total_win
        elif not self.in_free_spins:
            self.free_spin_winnings = 0
        self.last = result
        return result
