"""The player's chip stack, statistics and profile persistence.

There is exactly one :class:`Bank` per session and every game on the floor
draws from it, which is what makes chips carry between blackjack, the slots and
everything else.  The bank also owns the save file, so progress, statistics and
unlocked achievements survive between runs.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .. import config

SAVE_VERSION = 2

#: Identifiers used as keys in the per-game statistics table.
GAMES = (
    "blackjack",
    "holdem",
    "slots",
    "mines",
    "roulette",
    "videopoker",
    "crash",
)


class InsufficientChips(Exception):
    """Raised when a wager is larger than the stack backing it."""


@dataclass
class GameStats:
    """Lifetime numbers for a single game."""

    rounds: int = 0
    wagered: int = 0
    returned: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    biggest_win: int = 0
    biggest_bet: int = 0
    best_streak: int = 0
    current_streak: int = 0

    @property
    def net(self) -> int:
        """Chips won minus chips staked.  Negative means the house is up."""
        return self.returned - self.wagered

    @property
    def win_rate(self) -> float:
        decided = self.wins + self.losses
        return self.wins / decided if decided else 0.0

    @property
    def rtp(self) -> float:
        """Return to player: fraction of everything staked that came back."""
        return self.returned / self.wagered if self.wagered else 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GameStats":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class Achievement:
    key: str
    name: str
    description: str
    icon: str = "★"


ACHIEVEMENTS: Dict[str, Achievement] = {
    a.key: a
    for a in [
        Achievement("first_win", "First Blood", "Win your very first round."),
        Achievement("natural", "Natural 21", "Be dealt a blackjack.", "♠"),
        Achievement("five_card", "Five Card Charlie", "Draw five cards without busting."),
        Achievement("royal", "Royalty", "Make a royal flush.", "♥"),
        Achievement("quads", "Four of a Kind", "Make four of a kind."),
        Achievement("jackpot", "Jackpot!", "Land five matching symbols on the slots.", "♦"),
        Achievement("free_spins", "Free Ride", "Trigger the slots free spin bonus."),
        Achievement("diamond_hands", "Diamond Hands", "Cash out of Mines above 10x.", "♦"),
        Achievement("clean_sweep", "Clean Sweep", "Clear an entire Mines board."),
        Achievement("straight_up", "Straight Up", "Win a 35:1 single number on roulette."),
        Achievement("high_roller", "High Roller", "Place a single bet of 5,000 chips."),
        Achievement("comeback", "The Comeback", "Reach 5,000 chips after dropping below 100."),
        Achievement("millionaire", "Millionaire", "Hold 1,000,000 chips at once.", "♣"),
        Achievement("moon", "To The Moon", "Cash out of Crash above 25x."),
        Achievement("all_in", "All In", "Wager your entire stack and survive."),
        Achievement("tourist", "Tourist", "Play every game at least once."),
    ]
}


def _today() -> str:
    return _dt.date.today().isoformat()


class Bank:
    """A chip stack shared by the whole casino."""

    def __init__(self, chips: int = config.STARTING_CHIPS) -> None:
        self.chips = int(chips)
        self.peak_chips = int(chips)
        self.created_at = _dt.datetime.now().isoformat(timespec="seconds")
        self.last_bonus: str = ""
        self.bailouts = 0
        self.stats: Dict[str, GameStats] = {game: GameStats() for game in GAMES}
        self.achievements: set[str] = set()
        #: Sampled chip balance over time, drawn as a sparkline on the stats screen.
        self.balance_history: List[int] = [int(chips)]
        self.settings: Dict[str, object] = {
            "sfx": True,
            "music": True,
            "volume": 0.5,
            "fullscreen": False,
            "fast_deal": False,
        }
        self.fair: Dict[str, object] = {"client_seed": "pysino", "nonce": 0, "server_seed": ""}
        self._listeners: List[Callable[[str, int], None]] = []
        self._lowest_since_comeback = int(chips)

    # ------------------------------------------------------------- signals --
    def subscribe(self, callback: Callable[[str, int], None]) -> Callable[[], None]:
        """Register ``callback(reason, delta)``; returns an unsubscribe handle."""
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def _emit(self, reason: str, delta: int) -> None:
        for callback in list(self._listeners):
            callback(reason, delta)

    # ------------------------------------------------------------ economics --
    def stats_for(self, game: str) -> GameStats:
        return self.stats.setdefault(game, GameStats())

    def can_afford(self, amount: int) -> bool:
        return amount >= 0 and self.chips >= amount

    def wager(self, game: str, amount: int) -> int:
        """Move ``amount`` chips from the stack into play."""
        amount = int(amount)
        if amount < 0:
            raise ValueError("cannot wager a negative amount")
        if amount > self.chips:
            raise InsufficientChips(f"need {amount} chips, have {self.chips}")
        all_in = amount > 0 and amount == self.chips
        self.chips -= amount
        stats = self.stats_for(game)
        stats.wagered += amount
        stats.biggest_bet = max(stats.biggest_bet, amount)
        if amount >= 5_000:
            self.unlock("high_roller")
        if all_in:
            self._pending_all_in = True
        self._track_low()
        self._emit("wager", -amount)
        return amount

    def award(self, game: str, amount: int) -> int:
        """Pay ``amount`` chips back to the stack."""
        amount = int(amount)
        if amount < 0:
            raise ValueError("cannot award a negative amount")
        if amount == 0:
            return 0
        self.chips += amount
        self.stats_for(game).returned += amount
        self.peak_chips = max(self.peak_chips, self.chips)
        if self.chips >= 1_000_000:
            self.unlock("millionaire")
        if self.chips >= 5_000 and self._lowest_since_comeback < 100:
            self.unlock("comeback")
            self._lowest_since_comeback = self.chips
        self._emit("award", amount)
        return amount

    def finish_round(self, game: str, staked: int, returned: int) -> int:
        """Book the outcome of a completed round and return the net result."""
        stats = self.stats_for(game)
        stats.rounds += 1
        net = int(returned) - int(staked)
        if net > 0:
            stats.wins += 1
            stats.current_streak = max(1, stats.current_streak + 1)
            stats.best_streak = max(stats.best_streak, stats.current_streak)
            stats.biggest_win = max(stats.biggest_win, net)
            self.unlock("first_win")
            if getattr(self, "_pending_all_in", False):
                self.unlock("all_in")
        elif net < 0:
            stats.losses += 1
            stats.current_streak = min(-1, stats.current_streak - 1)
        else:
            stats.pushes += 1
        self._pending_all_in = False
        self.balance_history.append(self.chips)
        if len(self.balance_history) > 500:
            # Halve the resolution instead of dropping the early history, so the
            # sparkline still covers the player's whole career.
            self.balance_history = self.balance_history[::2]
        if all(self.stats_for(g).rounds > 0 for g in GAMES):
            self.unlock("tourist")
        self._track_low()
        self._emit("settle", net)
        return net

    def _track_low(self) -> None:
        self._lowest_since_comeback = min(self._lowest_since_comeback, self.chips)

    # --------------------------------------------------------- free money --
    @property
    def bonus_available(self) -> bool:
        return self.last_bonus != _today()

    def claim_daily_bonus(self) -> int:
        """Hand out the once-per-day top-up; returns 0 if already claimed."""
        if not self.bonus_available:
            return 0
        self.last_bonus = _today()
        self.chips += config.DAILY_BONUS_CHIPS
        self.peak_chips = max(self.peak_chips, self.chips)
        self._emit("bonus", config.DAILY_BONUS_CHIPS)
        return config.DAILY_BONUS_CHIPS

    @property
    def bailout_available(self) -> bool:
        return self.chips <= config.BAILOUT_THRESHOLD

    def claim_bailout(self) -> int:
        """Stake the player again once they are effectively broke."""
        if not self.bailout_available:
            return 0
        self.bailouts += 1
        self.chips += config.BAILOUT_CHIPS
        self._emit("bailout", config.BAILOUT_CHIPS)
        return config.BAILOUT_CHIPS

    # -------------------------------------------------------- achievements --
    def unlock(self, key: str) -> bool:
        """Unlock an achievement; True only the first time it happens."""
        if key not in ACHIEVEMENTS or key in self.achievements:
            return False
        self.achievements.add(key)
        self._emit("achievement", 0)
        self.pending_achievements.append(ACHIEVEMENTS[key])
        return True

    @property
    def pending_achievements(self) -> List[Achievement]:
        """Queue of newly unlocked achievements waiting to be shown as toasts."""
        if not hasattr(self, "_pending_achievements"):
            self._pending_achievements: List[Achievement] = []
        return self._pending_achievements

    # ------------------------------------------------------- totals for UI --
    @property
    def total_wagered(self) -> int:
        return sum(s.wagered for s in self.stats.values())

    @property
    def total_returned(self) -> int:
        return sum(s.returned for s in self.stats.values())

    @property
    def total_rounds(self) -> int:
        return sum(s.rounds for s in self.stats.values())

    @property
    def net(self) -> int:
        return self.total_returned - self.total_wagered

    # -------------------------------------------------------- persistence --
    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "chips": self.chips,
            "peak_chips": self.peak_chips,
            "created_at": self.created_at,
            "last_bonus": self.last_bonus,
            "bailouts": self.bailouts,
            "stats": {game: stats.to_dict() for game, stats in self.stats.items()},
            "achievements": sorted(self.achievements),
            "balance_history": self.balance_history[-500:],
            "settings": self.settings,
            "fair": self.fair,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Bank":
        bank = cls(int(data.get("chips", config.STARTING_CHIPS)))
        bank.peak_chips = int(data.get("peak_chips", bank.chips))
        bank.created_at = data.get("created_at", bank.created_at)
        bank.last_bonus = data.get("last_bonus", "")
        bank.bailouts = int(data.get("bailouts", 0))
        for game, stats in (data.get("stats") or {}).items():
            bank.stats[game] = GameStats.from_dict(stats)
        for game in GAMES:
            bank.stats.setdefault(game, GameStats())
        bank.achievements = set(data.get("achievements") or [])
        history = [int(v) for v in (data.get("balance_history") or [])]
        bank.balance_history = history or [bank.chips]
        bank.settings.update(data.get("settings") or {})
        bank.fair.update(data.get("fair") or {})
        bank._lowest_since_comeback = min(bank.balance_history + [bank.chips])
        return bank

    def save(self, path: Optional[Path] = None) -> Path:
        """Write the profile atomically so a crash can never truncate a save."""
        target = Path(path) if path else config.save_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.to_dict(), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
        return target

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Bank":
        """Load the profile, falling back to a fresh stack if it is unreadable."""
        target = Path(path) if path else config.save_path()
        try:
            with open(target, encoding="utf-8") as stream:
                return cls.from_dict(json.load(stream))
        except (OSError, ValueError, TypeError, KeyError):
            return cls()
