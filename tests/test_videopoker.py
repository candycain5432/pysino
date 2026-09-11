import random

import pytest

from pysino.core.cards import parse_hand
from pysino.games import videopoker as vp


@pytest.mark.parametrize(
    "hand,expected",
    [
        ("As Ks Qs Js 10s", vp.ROYAL_FLUSH),
        ("9h 8h 7h 6h 5h", vp.STRAIGHT_FLUSH),
        ("5h 4h 3h 2h Ah", vp.STRAIGHT_FLUSH),
        ("7h 7d 7c 7s 2h", vp.FOUR_OF_A_KIND),
        ("Kh Kd Kc 7s 7h", vp.FULL_HOUSE),
        ("Ah Kh 9h 5h 2h", vp.FLUSH),
        ("Ah 2d 3c 4s 5h", vp.STRAIGHT),
        ("Jh Jd Jc 5s 9h", vp.THREE_OF_A_KIND),
        ("Jh Jd 5c 5s 9h", vp.TWO_PAIR),
        ("Jh Jd 4c 5s 9h", vp.JACKS_OR_BETTER),
        ("Ah Ad 4c 5s 9h", vp.JACKS_OR_BETTER),
        ("10h 10d 4c 5s 9h", None),
        ("2h 5d 9c Js Kh", None),
    ],
)
def test_classification(hand, expected):
    assert vp.classify(parse_hand(hand)) == expected


def test_hands_must_be_five_cards():
    with pytest.raises(ValueError):
        vp.classify(parse_hand("As Ks Qs"))


def test_royal_flush_jumps_at_max_coins():
    assert vp.payout_for(vp.ROYAL_FLUSH, 4, 1) == 1_000
    assert vp.payout_for(vp.ROYAL_FLUSH, 5, 1) == 4_000


def test_paytable_is_linear_below_max_coins():
    for coins in range(1, 5):
        assert vp.payout_for(vp.FLUSH, coins, 10) == 60 * coins


def test_nine_six_schedule():
    assert vp.PAYTABLE[vp.FULL_HOUSE][0] == 9
    assert vp.PAYTABLE[vp.FLUSH][0] == 6


def test_a_miss_pays_nothing():
    assert vp.payout_for(None, 5, 10) == 0


def test_deal_hold_and_draw(rng):
    game = vp.VideoPokerGame(rng=rng)
    cards = game.deal(coins=5, coin_value=10)
    assert len(cards) == 5
    assert game.bet == 50
    assert game.state is vp.State.HOLDING

    game.set_holds([True, False, False, False, False])
    kept = game.cards[0]
    game.draw()
    assert game.state is vp.State.COMPLETE
    assert game.cards[0] == kept
    assert game.drawn == [1, 2, 3, 4]
    assert len(set(game.cards)) == 5


def test_holding_everything_draws_nothing(rng):
    game = vp.VideoPokerGame(rng=rng)
    dealt = list(game.deal(5, 10))
    game.set_holds([True] * 5)
    game.draw()
    assert game.cards == dealt
    assert game.drawn == []


def test_toggle_hold_flips_a_card(rng):
    game = vp.VideoPokerGame(rng=rng)
    game.deal(5, 10)
    assert game.toggle_hold(2) is True
    assert game.toggle_hold(2) is False


def test_cannot_draw_before_dealing(rng):
    with pytest.raises(RuntimeError):
        vp.VideoPokerGame(rng=rng).draw()


@pytest.mark.parametrize("coins", [0, 6])
def test_coin_count_is_validated(coins, rng):
    with pytest.raises(ValueError):
        vp.VideoPokerGame(rng=rng).deal(coins, 10)


def test_advisor_keeps_four_to_a_royal():
    advice = vp.best_hold(parse_hand("Ah Kh Qh Jh 3c"), random.Random(1))
    assert advice == (True, True, True, True, False)


def test_advisor_keeps_a_high_pair():
    advice = vp.best_hold(parse_hand("Jh Jd 4c 7s 9h"), random.Random(1))
    assert advice == (True, True, False, False, False)


def test_advisor_stands_pat_on_a_made_royal():
    advice = vp.best_hold(parse_hand("As Ks Qs Js 10s"), random.Random(1))
    assert advice == (True,) * 5


def test_advisor_breaks_a_low_pair_for_four_to_a_flush():
    # Four hearts plus an off-suit pair of deuces: the flush draw is worth more.
    advice = vp.best_hold(parse_hand("2h 5h 9h Kh 2c"), random.Random(1))
    assert advice == (True, True, True, True, False)


def test_advisor_always_returns_five_flags():
    rng = random.Random(8)
    game = vp.VideoPokerGame(rng=rng)
    for _ in range(5):
        cards = game.deal(5, 10)
        advice = vp.best_hold(cards, rng, samples=80)
        assert len(advice) == 5
        game.set_holds(advice)
        game.draw()
