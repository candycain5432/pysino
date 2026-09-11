"""No-limit Texas Hold'em against Monte Carlo bots.

Implements a full cash-game hand: blinds, four betting streets, correct
short-stack all-in handling and layered side pots.  The bots estimate their
equity by simulating the rest of the hand a few hundred times and mix that with
pot odds and a personality to decide what to do.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from ..core.cards import Card, Deck, full_deck
from ..core.poker import HandRank, evaluate


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


#: How many community cards are face up on each street.
BOARD_SIZE = {
    Street.PREFLOP: 0,
    Street.FLOP: 3,
    Street.TURN: 4,
    Street.RIVER: 5,
    Street.SHOWDOWN: 5,
    Street.COMPLETE: 5,
}


class Action(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"


@dataclass
class AIProfile:
    """Knobs that give each bot a recognisable style."""

    name: str
    #: Equity needed before the bot is happy to put money in.
    tightness: float = 0.5
    #: How often a good hand becomes a raise rather than a call.
    aggression: float = 0.4
    #: Chance of firing at a pot with nothing.
    bluff: float = 0.08
    #: Monte Carlo samples per decision; higher is slower but sharper.
    iterations: int = 240


PROFILES = (
    AIProfile("Rock", tightness=0.62, aggression=0.25, bluff=0.02),
    AIProfile("Shark", tightness=0.50, aggression=0.55, bluff=0.12),
    AIProfile("Maniac", tightness=0.38, aggression=0.75, bluff=0.28),
    AIProfile("Calling Station", tightness=0.42, aggression=0.10, bluff=0.03),
    AIProfile("Grinder", tightness=0.55, aggression=0.40, bluff=0.07),
)


@dataclass
class Player:
    name: str
    chips: int
    seat: int
    is_human: bool = False
    profile: Optional[AIProfile] = None
    hole: List[Card] = field(default_factory=list)
    #: Chips pushed forward on the current street.
    bet: int = 0
    #: Chips pushed forward across the whole hand.
    committed: int = 0
    folded: bool = False
    all_in: bool = False
    has_acted: bool = False
    last_action: str = ""
    sitting_out: bool = False
    won_last: int = 0

    @property
    def in_hand(self) -> bool:
        return not self.folded and not self.sitting_out

    @property
    def can_act(self) -> bool:
        return self.in_hand and not self.all_in


@dataclass
class Pot:
    """One layer of the pot, with the players entitled to contest it."""

    amount: int
    eligible: List[Player]
    is_side: bool = False


@dataclass
class ShowdownEntry:
    player: Player
    rank: Optional[HandRank]
    won: int = 0


@dataclass
class HandResult:
    winners: List[Player]
    entries: List[ShowdownEntry]
    pots: List[Pot]
    board: List[Card]
    went_to_showdown: bool


def build_pots(players: Sequence[Player]) -> List[Pot]:
    """Split contributions into a main pot and any side pots.

    Folded players' chips still form part of the pot they paid into, they are
    simply not eligible to win it.
    """
    contributors = [p for p in players if p.committed > 0]
    if not contributors:
        return []

    levels = sorted({p.committed for p in contributors})
    pots: List[Pot] = []
    previous = 0
    for level in levels:
        amount = 0
        for player in contributors:
            amount += max(0, min(player.committed, level) - previous)
        eligible = [p for p in contributors if p.committed >= level and p.in_hand]
        previous = level
        if amount <= 0:
            continue
        # Consecutive layers contested by exactly the same players are really
        # one pot; without this a player folding their blind would look like it
        # had created a side pot.
        if pots and [id(x) for x in pots[-1].eligible] == [id(x) for x in eligible]:
            pots[-1].amount += amount
        else:
            pots.append(Pot(amount=amount, eligible=eligible, is_side=bool(pots)))
    return pots


def estimate_equity(
    hole: Sequence[Card],
    board: Sequence[Card],
    opponents: int,
    rng,
    iterations: int = 240,
) -> float:
    """Probability of winning (ties counted as half) by random simulation."""
    if opponents <= 0:
        return 1.0
    known = set(hole) | set(board)
    deck = [card for card in full_deck() if card not in known]
    needed = 5 - len(board)
    draw = needed + 2 * opponents
    if draw > len(deck):
        return 0.0

    score = 0.0
    for _ in range(iterations):
        sample = rng.sample(deck, draw)
        runout = list(board) + sample[:needed]
        mine = evaluate(list(hole) + runout).value
        best_other = -1
        cursor = needed
        for _ in range(opponents):
            other = evaluate(sample[cursor:cursor + 2] + runout).value
            cursor += 2
            if other > best_other:
                best_other = other
        if mine > best_other:
            score += 1.0
        elif mine == best_other:
            score += 0.5
    return score / iterations


class HoldemGame:
    """A no-limit hold'em cash table."""

    def __init__(
        self,
        rng,
        players: Sequence[Player],
        small_blind: int = 10,
        big_blind: int = 20,
    ) -> None:
        if len(players) < 2:
            raise ValueError("hold'em needs at least two players")
        self.rng = rng
        self.players: List[Player] = list(players)
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.button = 0
        self.street = Street.COMPLETE
        self.board: List[Card] = []
        self.deck: Optional[Deck] = None
        self.current_bet = 0
        self.min_raise = big_blind
        self.to_act: Optional[int] = None
        self.result: Optional[HandResult] = None
        self.hand_number = 0
        self.log: List[str] = []

    # ------------------------------------------------------------ queries --
    @property
    def pot(self) -> int:
        return sum(player.committed for player in self.players)

    @property
    def contenders(self) -> List[Player]:
        return [player for player in self.players if player.in_hand]

    @property
    def seated(self) -> List[Player]:
        return [player for player in self.players if not player.sitting_out]

    @property
    def current_player(self) -> Optional[Player]:
        if self.to_act is None:
            return None
        return self.players[self.to_act]

    @property
    def is_hand_over(self) -> bool:
        return self.street in (Street.SHOWDOWN, Street.COMPLETE)

    def to_call(self, player: Player) -> int:
        return max(0, min(self.current_bet - player.bet, player.chips))

    def min_raise_to(self, player: Player) -> int:
        """Smallest legal total bet for a raise, capped by the player's stack."""
        target = max(self.current_bet + self.min_raise, self.big_blind)
        return min(target, player.bet + player.chips)

    def max_raise_to(self, player: Player) -> int:
        return player.bet + player.chips

    def legal_actions(self, player: Optional[Player] = None) -> List[Action]:
        player = player or self.current_player
        if player is None or self.is_hand_over or not player.can_act:
            return []
        owed = self.to_call(player)
        actions = [Action.FOLD] if owed > 0 else [Action.CHECK]
        if owed > 0:
            actions.append(Action.CALL)
        # A raise needs chips beyond the call, and at least two players who can
        # still act - raising into a table of all-ins is meaningless.
        others_live = [p for p in self.contenders if p is not player and not p.all_in]
        if player.chips > owed and others_live:
            actions.append(Action.RAISE if self.current_bet > 0 else Action.BET)
        return actions

    # -------------------------------------------------------- hand set-up --
    def start_hand(self) -> None:
        """Shuffle up and deal; blinds are posted automatically."""
        for player in self.players:
            player.sitting_out = player.chips <= 0
            player.hole = []
            player.bet = 0
            player.committed = 0
            player.folded = player.sitting_out
            player.all_in = False
            player.has_acted = False
            player.last_action = ""
            player.won_last = 0

        if len(self.seated) < 2:
            raise RuntimeError("not enough funded players to start a hand")

        self.hand_number += 1
        self.log = []
        self.deck = Deck(self.rng)
        self.board = []
        self.result = None
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.street = Street.PREFLOP

        self._move_button()
        order = self.seated
        count = len(order)
        if count == 2:
            small_index, big_index = 0, 1
            # Heads up the button posts the small blind and acts first preflop.
            order = self._rotate(order, order.index(self.players[self.button]))
        else:
            order = self._rotate(order, (order.index(self.players[self.button]) + 1) % count)
            small_index, big_index = 0, 1

        self._post(order[small_index], self.small_blind, "small blind")
        self._post(order[big_index], self.big_blind, "big blind")
        self.current_bet = self.big_blind

        for player in self.seated:
            player.hole = self.deck.deal(2)

        first = order[(big_index + 1) % count]
        self.to_act = self.players.index(first)
        self._skip_to_actionable()

    def _move_button(self) -> None:
        for _ in range(len(self.players)):
            self.button = (self.button + 1) % len(self.players)
            if not self.players[self.button].sitting_out:
                return

    @staticmethod
    def _rotate(items: List[Player], start: int) -> List[Player]:
        return items[start:] + items[:start]

    def _post(self, player: Player, amount: int, label: str) -> None:
        posted = min(amount, player.chips)
        player.chips -= posted
        player.bet += posted
        player.committed += posted
        if player.chips == 0:
            player.all_in = True
        self.log.append(f"{player.name} posts the {label} ({posted})")

    # ---------------------------------------------------------- acting --
    def act(self, action: Action, amount: int = 0) -> None:
        """Apply ``action`` for the player whose turn it is."""
        player = self.current_player
        if player is None or self.is_hand_over:
            raise RuntimeError("no action is pending")
        if action not in self.legal_actions(player):
            raise RuntimeError(f"{action.value} is not legal here")

        if action is Action.FOLD:
            player.folded = True
            player.last_action = "Fold"
            self.log.append(f"{player.name} folds")
        elif action is Action.CHECK:
            player.last_action = "Check"
            self.log.append(f"{player.name} checks")
        elif action is Action.CALL:
            paid = self._commit(player, self.to_call(player))
            player.last_action = "All in" if player.all_in else f"Call {paid}"
            self.log.append(f"{player.name} calls {paid}")
        else:
            self._apply_raise(player, amount)

        player.has_acted = True
        self._after_action()

    def _apply_raise(self, player: Player, target: int) -> None:
        low, high = self.min_raise_to(player), self.max_raise_to(player)
        target = max(low, min(int(target), high))
        increase = target - self.current_bet
        paid = self._commit(player, target - player.bet)

        # An all-in that falls short of a full raise does not reopen betting
        # for players who have already acted.
        reopens = increase >= self.min_raise
        if reopens:
            self.min_raise = increase
        previous_bet = self.current_bet
        self.current_bet = max(self.current_bet, player.bet)

        verb = "bets" if previous_bet == 0 else "raises to"
        player.last_action = "All in" if player.all_in else f"{verb.split()[0].title()} {player.bet}"
        self.log.append(f"{player.name} {verb} {player.bet}" + (" and is all in" if player.all_in else ""))

        if reopens:
            for other in self.contenders:
                if other is not player and not other.all_in:
                    other.has_acted = False

    def _commit(self, player: Player, amount: int) -> int:
        paid = max(0, min(amount, player.chips))
        player.chips -= paid
        player.bet += paid
        player.committed += paid
        if player.chips == 0:
            player.all_in = True
        return paid

    def _after_action(self) -> None:
        if len(self.contenders) <= 1:
            self._finish_without_showdown()
            return
        if self._betting_complete():
            self._advance_street()
        else:
            self._next_player()

    def _betting_complete(self) -> bool:
        actionable = [player for player in self.contenders if not player.all_in]
        if not actionable:
            return True
        return all(
            player.has_acted and player.bet == self.current_bet for player in actionable
        )

    def _next_player(self) -> None:
        assert self.to_act is not None
        for step in range(1, len(self.players) + 1):
            index = (self.to_act + step) % len(self.players)
            if self.players[index].can_act:
                self.to_act = index
                return
        self.to_act = None

    def _skip_to_actionable(self) -> None:
        """Make sure ``to_act`` points at somebody who can actually act."""
        if self.to_act is None:
            return
        if self.players[self.to_act].can_act:
            return
        self._next_player()

    # --------------------------------------------------------- streets --
    def _advance_street(self) -> None:
        for player in self.players:
            player.bet = 0
            player.has_acted = False
        self.current_bet = 0
        self.min_raise = self.big_blind

        assert self.deck is not None
        if self.street is Street.PREFLOP:
            self.street = Street.FLOP
            self.board.extend(self.deck.deal(3))
        elif self.street is Street.FLOP:
            self.street = Street.TURN
            self.board.append(self.deck.draw())
        elif self.street is Street.TURN:
            self.street = Street.RIVER
            self.board.append(self.deck.draw())
        else:
            self._showdown()
            return

        actionable = [player for player in self.contenders if not player.all_in]
        if len(actionable) <= 1:
            # Everyone is committed; run the rest of the board out unattended.
            self.to_act = None
            self._advance_street()
            return

        first = self._first_to_act_postflop()
        self.to_act = self.players.index(first) if first else None
        self._skip_to_actionable()

    def _first_to_act_postflop(self) -> Optional[Player]:
        order = self.seated
        if not order:
            return None
        start = (order.index(self.players[self.button]) + 1) % len(order)
        for step in range(len(order)):
            candidate = order[(start + step) % len(order)]
            if candidate.can_act:
                return candidate
        return None

    # --------------------------------------------------------- settling --
    def _finish_without_showdown(self) -> None:
        winner = next((player for player in self.players if player.in_hand), None)
        pots = build_pots(self.players)
        entries = [ShowdownEntry(player=winner, rank=None)] if winner else []
        if winner:
            total = sum(pot.amount for pot in pots)
            winner.chips += total
            winner.won_last = total
            entries[0].won = total
            self.log.append(f"{winner.name} wins {total} uncontested")
        self.street = Street.COMPLETE
        self.to_act = None
        self.result = HandResult(
            winners=[winner] if winner else [],
            entries=entries,
            pots=pots,
            board=list(self.board),
            went_to_showdown=False,
        )

    def _showdown(self) -> None:
        assert self.deck is not None
        while len(self.board) < 5:
            self.board.append(self.deck.draw())

        self.street = Street.SHOWDOWN
        self.to_act = None
        contenders = self.contenders
        ranks: Dict[int, HandRank] = {
            id(player): evaluate(player.hole + self.board) for player in contenders
        }
        entries = [
            ShowdownEntry(player=player, rank=ranks[id(player)]) for player in contenders
        ]
        by_player = {id(entry.player): entry for entry in entries}

        pots = build_pots(self.players)
        for pot in pots:
            eligible = [player for player in pot.eligible if player in contenders]
            if not eligible:
                continue
            best = max(ranks[id(player)].value for player in eligible)
            winners = [player for player in eligible if ranks[id(player)].value == best]
            share, remainder = divmod(pot.amount, len(winners))
            for index, player in enumerate(winners):
                # Odd chips go to the first winner left of the button.
                extra = 1 if index < remainder else 0
                player.chips += share + extra
                player.won_last += share + extra
                by_player[id(player)].won += share + extra

        overall = max((entry.won for entry in entries), default=0)
        self.result = HandResult(
            winners=[entry.player for entry in entries if entry.won == overall and overall > 0],
            entries=entries,
            pots=pots,
            board=list(self.board),
            went_to_showdown=True,
        )
        for entry in entries:
            if entry.rank:
                self.log.append(f"{entry.player.name} shows {entry.rank.describe()}")
        self.street = Street.COMPLETE

    # -------------------------------------------------------------- bots --
    def ai_decision(self, player: Optional[Player] = None) -> Tuple[Action, int]:
        """Work out what a bot wants to do, without applying it."""
        player = player or self.current_player
        if player is None:
            raise RuntimeError("nobody is to act")
        profile = player.profile or PROFILES[1]
        actions = self.legal_actions(player)
        if not actions:
            raise RuntimeError("no legal actions")

        opponents = max(1, len([p for p in self.contenders if p is not player]))
        equity = estimate_equity(
            player.hole, self.board, opponents, self.rng, profile.iterations
        )

        owed = self.to_call(player)
        pot = self.pot
        pot_odds = owed / (pot + owed) if owed else 0.0
        roll = self.rng.random()

        # Scale the raw simulation result by how willing this bot is to commit.
        confidence = equity - (profile.tightness - 0.5) * 0.25

        if owed == 0:
            wants_value = confidence > 0.58 and roll < 0.35 + profile.aggression
            wants_bluff = confidence < 0.35 and roll < profile.bluff
            if (wants_value or wants_bluff) and (Action.BET in actions or Action.RAISE in actions):
                sizing = 0.5 + profile.aggression * 0.5
                target = max(self.min_raise_to(player), int(pot * sizing))
                return (Action.BET if Action.BET in actions else Action.RAISE,
                        min(target, self.max_raise_to(player)))
            return (Action.CHECK, 0)

        if confidence < pot_odds - 0.02:
            # Priced out, though a tiny call against a big pot is still fine.
            cheap = owed <= player.chips * 0.03 and confidence > 0.2
            if not cheap and roll > profile.bluff:
                return (Action.FOLD, 0)

        if confidence > 0.72 and roll < profile.aggression + 0.25 and (
            Action.RAISE in actions or Action.BET in actions
        ):
            sizing = 0.6 + profile.aggression * 0.6
            target = max(self.min_raise_to(player), int((pot + owed) * sizing))
            return (Action.RAISE if Action.RAISE in actions else Action.BET,
                    min(target, self.max_raise_to(player)))

        if Action.CALL in actions:
            return (Action.CALL, 0)
        return (Action.CHECK, 0) if Action.CHECK in actions else (Action.FOLD, 0)

    def play_ai_turn(self) -> Tuple[Action, int]:
        action, amount = self.ai_decision()
        self.act(action, amount)
        return action, amount


def make_table(
    rng,
    human_stack: int,
    bot_count: int = 3,
    bot_stack: int = 2_000,
    human_name: str = "You",
) -> List[Player]:
    """Seat a human plus ``bot_count`` bots with distinct personalities."""
    profiles = list(PROFILES)
    rng.shuffle(profiles)
    players = [Player(name=human_name, chips=human_stack, seat=0, is_human=True)]
    for index in range(bot_count):
        profile = profiles[index % len(profiles)]
        players.append(
            Player(name=profile.name, chips=bot_stack, seat=index + 1, profile=profile)
        )
    return players
