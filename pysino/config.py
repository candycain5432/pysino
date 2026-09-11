"""Global configuration: screen geometry, filesystem paths and tunable rules.

Everything the rest of the package needs to know about "where things live" is
resolved here so tests can redirect state with a single environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- rendering --
# The whole game is drawn onto a fixed-size surface at this resolution and then
# scaled to fit whatever window the player has.  Layout code can therefore use
# absolute coordinates without caring about the real window size.
BASE_WIDTH = 1280
BASE_HEIGHT = 720
BASE_SIZE = (BASE_WIDTH, BASE_HEIGHT)

FPS = 60
WINDOW_TITLE = "Pysino"

# ------------------------------------------------------------------- economy --
STARTING_CHIPS = 1_000
#: Handed out when a player is broke and asks for a top-up.
BAILOUT_CHIPS = 500
#: A bailout is only offered once the stack drops to (or below) this.
BAILOUT_THRESHOLD = 50
#: Free chips claimable once per real-world day.
DAILY_BONUS_CHIPS = 750

CHIP_DENOMINATIONS = (1, 5, 25, 100, 500, 2_500)

# ------------------------------------------------------------------- storage --


def save_dir() -> Path:
    """Directory holding the profile.  Override with ``PYSINO_HOME`` for tests."""
    override = os.environ.get("PYSINO_HOME")
    root = Path(override) if override else Path.home() / ".pysino"
    return root


def save_path() -> Path:
    return save_dir() / "profile.json"


# -------------------------------------------------------------- house rules --
BLACKJACK_DECKS = 6
#: Reshuffle once this fraction of the shoe has been dealt.
SHOE_PENETRATION = 0.75
#: Dealer hits soft 17 when True.
DEALER_HITS_SOFT_17 = False
BLACKJACK_PAYOUT = 1.5
MAX_SPLIT_HANDS = 4

#: Fraction of every wager the house keeps on the maths-driven games.
HOUSE_EDGE = 0.01

MIN_BET = 1
MAX_BET = 100_000
