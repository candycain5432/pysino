"""Mines: uncover gems on a grid, cash out before you hit a bomb.

The multiplier after ``k`` safe picks is the inverse of the probability of
getting that far, scaled down by the house edge::

    multiplier(k) = (1 - edge) / P(k consecutive safe picks)

which makes every cash-out point carry exactly the same expected return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import comb
from typing import List, Optional, Set

from .. import config

GRID_SIZE = 5
TILE_COUNT = GRID_SIZE * GRID_SIZE
MIN_MINES = 1
MAX_MINES = 24


class State(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    BUSTED = "busted"
    CASHED = "cashed"


def safe_probability(mines: int, picks: int) -> float:
    """Probability of making ``picks`` safe picks in a row."""
    safe = TILE_COUNT - mines
    if picks > safe:
        return 0.0
    return comb(safe, picks) / comb(TILE_COUNT, picks)


def multiplier_for(mines: int, picks: int, edge: float = config.HOUSE_EDGE) -> float:
    """Payout multiplier after ``picks`` successful reveals."""
    if picks <= 0:
        return 1.0
    probability = safe_probability(mines, picks)
    if probability <= 0.0:
        raise ValueError("more picks than there are safe tiles")
    return (1.0 - edge) / probability


def multiplier_table(mines: int, edge: float = config.HOUSE_EDGE) -> List[float]:
    """Every multiplier from one pick up to clearing the board."""
    safe = TILE_COUNT - mines
    return [multiplier_for(mines, picks, edge) for picks in range(1, safe + 1)]


@dataclass
class MinesGame:
    """One board.  Mines are placed up front but never revealed until the end."""

    rng: object
    mines: int = 3
    bet: int = 0
    edge: float = config.HOUSE_EDGE
    state: State = State.IDLE
    mine_positions: Set[int] = field(default_factory=set)
    revealed: List[int] = field(default_factory=list)
    hit_position: Optional[int] = None

    def start(self, bet: int, mines: int) -> None:
        """Lay a new board.  ``bet`` chips must already have left the bank."""
        if bet <= 0:
            raise ValueError("bet must be positive")
        if not MIN_MINES <= mines <= MAX_MINES:
            raise ValueError(f"mines must be between {MIN_MINES} and {MAX_MINES}")
        self.bet = int(bet)
        self.mines = int(mines)
        self.mine_positions = set(self.rng.sample(range(TILE_COUNT), self.mines))
        self.revealed = []
        self.hit_position = None
        self.state = State.PLAYING

    # ------------------------------------------------------------ progress --
    @property
    def picks(self) -> int:
        return len(self.revealed)

    @property
    def safe_tiles(self) -> int:
        return TILE_COUNT - self.mines

    @property
    def multiplier(self) -> float:
        return multiplier_for(self.mines, self.picks, self.edge) if self.picks else 1.0

    @property
    def payout(self) -> int:
        """What cashing out right now would return, stake included."""
        return int(self.bet * self.multiplier) if self.picks else self.bet

    @property
    def next_multiplier(self) -> Optional[float]:
        if self.picks >= self.safe_tiles:
            return None
        return multiplier_for(self.mines, self.picks + 1, self.edge)

    @property
    def is_cleared(self) -> bool:
        return self.picks >= self.safe_tiles

    def reveal(self, position: int) -> bool:
        """Uncover a tile.  Returns True when it was safe."""
        if self.state is not State.PLAYING:
            raise RuntimeError("no board in play")
        if not 0 <= position < TILE_COUNT:
            raise ValueError("position off the board")
        if position in self.revealed:
            raise ValueError("tile already revealed")

        if position in self.mine_positions:
            self.hit_position = position
            self.state = State.BUSTED
            return False

        self.revealed.append(position)
        if self.is_cleared:
            # Clearing the board is an automatic, maximum-multiplier cash out.
            self.state = State.CASHED
        return True

    def cash_out(self) -> int:
        """Bank the current multiplier; returns the gross payout."""
        if self.state is State.CASHED:
            return self.payout
        if self.state is not State.PLAYING:
            raise RuntimeError("nothing to cash out")
        if not self.revealed:
            raise RuntimeError("reveal at least one tile before cashing out")
        self.state = State.CASHED
        return self.payout
