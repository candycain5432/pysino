"""Crash: a multiplier climbs from 1.00x and dies at a random point.

The crash point is drawn so that ``P(crash >= x) = (1 - edge) / x``.  Cashing
out at any target therefore returns the same expected value, and the curve has
the heavy tail that makes the game interesting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .. import config


class State(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    CASHED = "cashed"
    CRASHED = "crashed"


def draw_crash_point(rng, edge: float = config.HOUSE_EDGE) -> float:
    """Sample a crash multiplier, rounded down to two decimals."""
    raw = (1.0 - edge) / (1.0 - rng.random())
    # When the draw lands below 1.00x the round busts instantly.  That happens
    # with probability exactly ``edge``, which is where the house edge lives -
    # it must not also be subtracted anywhere else.
    return max(1.0, int(raw * 100) / 100.0)


#: How fast the multiplier climbs; tuned so early seconds feel tense but slow.
GROWTH_RATE = 0.07


def multiplier_at(elapsed: float) -> float:
    """The multiplier ``elapsed`` seconds into a run (exponential growth)."""
    return max(1.0, round((1.0 + GROWTH_RATE) ** (elapsed * 4.0), 2))


def time_for_multiplier(multiplier: float) -> float:
    """Inverse of :func:`multiplier_at`, used to schedule the crash moment."""
    from math import log

    if multiplier <= 1.0:
        return 0.0
    return log(multiplier) / (log(1.0 + GROWTH_RATE) * 4.0)


@dataclass
class CrashGame:
    rng: object
    edge: float = config.HOUSE_EDGE
    state: State = State.IDLE
    bet: int = 0
    crash_point: float = 1.0
    cashed_at: Optional[float] = None
    auto_cash_out: Optional[float] = None
    elapsed: float = 0.0

    def start(self, bet: int, auto_cash_out: Optional[float] = None) -> float:
        if bet <= 0:
            raise ValueError("bet must be positive")
        self.bet = int(bet)
        self.crash_point = draw_crash_point(self.rng, self.edge)
        self.auto_cash_out = auto_cash_out
        self.cashed_at = None
        self.elapsed = 0.0
        self.state = State.RUNNING
        return self.crash_point

    @property
    def multiplier(self) -> float:
        if self.state is State.CASHED and self.cashed_at is not None:
            return self.cashed_at
        if self.state is State.CRASHED:
            return self.crash_point
        return min(multiplier_at(self.elapsed), self.crash_point)

    @property
    def payout(self) -> int:
        if self.state is not State.CASHED or self.cashed_at is None:
            return 0
        return int(self.bet * self.cashed_at)

    def tick(self, delta: float) -> None:
        """Advance the run; auto cash-out fires the instant it is reached."""
        if self.state is not State.RUNNING:
            return
        self.elapsed += delta
        current = multiplier_at(self.elapsed)
        target = self.auto_cash_out
        if target and current >= target and target <= self.crash_point:
            self.cashed_at = target
            self.state = State.CASHED
            return
        if current >= self.crash_point:
            self.state = State.CRASHED

    def cash_out(self) -> int:
        """Take the money and run.  Returns the gross payout."""
        if self.state is not State.RUNNING:
            raise RuntimeError("nothing running to cash out")
        self.cashed_at = self.multiplier
        self.state = State.CASHED
        return self.payout
