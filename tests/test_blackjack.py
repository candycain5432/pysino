import random

import pytest

from pysino.core.cards import Card, parse_hand
from pysino.games.blackjack import (
    Action, BlackjackGame, Hand, Outcome, Rules, State, basic_strategy, hand_value,
)


def stacked(cards, bet=10, rules=None):
    """A dealt game whose shoe delivers ``cards`` in the order written.

    Deal order is player, dealer, player, dealer - so the first four cards are
    the player's two and the dealer's two, interleaved.
    """
    game = BlackjackGame(random.Random(0), rules)
    game.shoe._cards = list(reversed(parse_hand(cards)))
    game.shoe._dealt = 0
    game.start_round(bet)
    return game


@pytest.mark.parametrize(
    "hand,total,soft",
    [
        ("As Ks", 21, True),
        ("As As", 12, True),
        ("As As As", 13, True),
        ("As 9h 5d", 15, False),
        ("Ks Qh 5d", 25, False),
        ("5s 6h", 11, False),
        ("As 6h", 17, True),
        ("As 6h 10d", 17, False),
    ],
)
def test_hand_values(hand, total, soft):
    assert hand_value(parse_hand(hand)) == (total, soft)


def test_natural_blackjack_pays_three_to_two():
    # Deal order is player, dealer, player, dealer.
    game = stacked("As 9h Kd 8c")
    assert game.state is State.DONE
    hand = game.hands[0]
    assert hand.is_blackjack
    assert hand.outcome is Outcome.BLACKJACK
    assert hand.payout == 25  # 10 stake + 15 winnings
    game_result = game.result
    assert game_result.net == 15


def test_both_blackjack_is_a_push():
    game = stacked("As Ah Kd Kc")
    assert game.state is State.INSURANCE
    game.decline_insurance()
    assert game.hands[0].outcome is Outcome.PUSH
    assert game.hands[0].payout == 10


def test_dealer_blackjack_beats_a_normal_hand():
    game = stacked("5s Ah 6d Kc")
    game.decline_insurance()
    assert game.hands[0].outcome is Outcome.LOSE
    assert game.result.returned == 0


def test_insurance_pays_two_to_one_when_the_dealer_has_it():
    game = stacked("5s Ah 6d Kc")
    assert game.state is State.INSURANCE
    cost = game.take_insurance()
    assert cost == 5
    assert game.result.insurance_payout == 15
    assert game.result.staked == 15
    assert game.result.returned == 15  # hand loses, insurance covers it


def test_declined_insurance_costs_nothing():
    game = stacked("5s Ah 6d Kc")
    game.decline_insurance()
    assert game.result.insurance_bet == 0
    assert game.result.staked == 10


def test_player_bust_loses_immediately():
    game = stacked("10s 5h 9d 8c 5s")
    game.hit()
    assert game.hands[0].is_busted
    assert game.hands[0].outcome is Outcome.BUST
    assert game.result.returned == 0


def test_dealer_stands_on_soft_17_by_default():
    game = stacked("10s 6h 9d Ac")
    game.stand()
    assert game.dealer_total == 17
    assert game.hands[0].outcome is Outcome.WIN


def test_dealer_hits_soft_17_when_configured():
    game = stacked("10s 6h 9d Ac 3h", rules=Rules(dealer_hits_soft_17=True))
    game.stand()
    assert game.dealer_total == 20
    assert game.hands[0].outcome is Outcome.LOSE


def test_double_adds_one_card_and_doubles_the_bet():
    game = stacked("5s 9h 6d 8c 10h")
    extra, card = game.double()
    assert extra == 10
    assert game.hands[0].bet == 20
    assert len(game.hands[0].cards) == 3
    assert game.state is State.DONE


def test_split_creates_two_hands_each_with_its_own_bet():
    game = stacked("8s 9h 8d 8c 3h 5s 7d")
    assert Action.SPLIT in game.available_actions()
    extra = game.split()
    assert extra == 10
    assert len(game.hands) == 2
    assert all(len(hand.cards) == 2 for hand in game.hands)
    assert all(hand.from_split for hand in game.hands)


def test_split_aces_get_one_card_each_and_stand():
    game = stacked("As 9h Ad 8c 5h 7s")
    game.split()
    assert game.state is State.DONE
    assert all(len(hand.cards) == 2 for hand in game.hands)


def test_split_hand_21_is_not_a_blackjack():
    hand = Hand(cards=parse_hand("As Ks"), from_split=True)
    assert hand.total == 21
    assert not hand.is_blackjack


def test_cannot_split_past_the_hand_limit():
    game = stacked("8s 9h 8d 8c 8h 8d 8c 8s 8h", rules=Rules(max_hands=2))
    game.split()
    assert Action.SPLIT not in game.available_actions()


def test_surrender_returns_half_the_bet():
    game = stacked("10s 9h 6d Kc")
    assert Action.SURRENDER in game.available_actions()
    game.surrender()
    assert game.hands[0].outcome is Outcome.SURRENDER
    assert game.hands[0].payout == 5


def test_surrender_is_unavailable_after_hitting():
    game = stacked("10s 9h 2d Kc 3h")
    game.hit()
    assert Action.SURRENDER not in game.available_actions()


def test_illegal_actions_are_refused():
    game = stacked("10s 9h 6d Kc 4h")
    game.stand()
    with pytest.raises(RuntimeError):
        game.hit()


def test_push_returns_the_stake():
    game = stacked("10s 9h 9d 10c")
    game.stand()
    assert game.hands[0].outcome is Outcome.PUSH
    assert game.result.net == 0


def test_dealer_does_not_draw_when_every_hand_busted():
    game = stacked("10s 6h 9d 5c 5h 2d")
    game.hit()
    assert game.hands[0].is_busted
    assert len(game.dealer_cards) == 2


def test_five_card_charlie_is_flagged():
    hand = Hand(cards=parse_hand("2s 3h 4d 5c 6s"))
    assert hand.is_charlie


def test_basic_strategy_always_returns_a_legal_action(rng):
    game = BlackjackGame(rng)
    for _ in range(400):
        game.start_round(10)
        if game.state is State.INSURANCE:
            game.decline_insurance()
        while game.state is State.PLAYER:
            actions = game.available_actions()
            choice = basic_strategy(game.active_hand, game.dealer_upcard, actions)
            assert choice in actions
            {
                Action.HIT: game.hit, Action.STAND: game.stand,
                Action.DOUBLE: game.double, Action.SPLIT: game.split,
                Action.SURRENDER: game.surrender,
            }[choice]()


def test_basic_strategy_hits_a_stiff_against_a_ten():
    hand = Hand(cards=parse_hand("10s 6h"))
    assert basic_strategy(hand, Card.parse("Kd"), [Action.HIT, Action.STAND]) is Action.HIT


def test_basic_strategy_stands_on_a_stiff_against_a_six():
    hand = Hand(cards=parse_hand("10s 6h"))
    assert basic_strategy(hand, Card.parse("6d"), [Action.HIT, Action.STAND]) is Action.STAND


def test_basic_strategy_always_splits_aces_and_eights():
    for pair in ("As Ad", "8s 8d"):
        hand = Hand(cards=parse_hand(pair))
        actions = [Action.HIT, Action.STAND, Action.SPLIT]
        assert basic_strategy(hand, Card.parse("9d"), actions) is Action.SPLIT


def test_house_edge_is_small_under_basic_strategy():
    """A long simulation should land near the theoretical edge, not miles off."""
    game = BlackjackGame(random.Random(20_250_911))
    staked = returned = 0
    for _ in range(20_000):
        game.start_round(10)
        if game.state is State.INSURANCE:
            game.decline_insurance()
        while game.state is State.PLAYER:
            choice = basic_strategy(
                game.active_hand, game.dealer_upcard, game.available_actions()
            )
            {
                Action.HIT: game.hit, Action.STAND: game.stand,
                Action.DOUBLE: game.double, Action.SPLIT: game.split,
                Action.SURRENDER: game.surrender,
            }[choice]()
        staked += game.result.staked
        returned += game.result.returned
    edge = (staked - returned) / staked
    assert -0.02 < edge < 0.03, f"house edge {edge:.4f} is implausible"
