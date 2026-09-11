import pytest

from pysino.core import poker
from pysino.core.cards import parse_hand
from pysino.core.poker import compare, evaluate


@pytest.mark.parametrize(
    "hand,category",
    [
        ("As Ks Qs Js 10s", poker.STRAIGHT_FLUSH),
        ("5s 4s 3s 2s As", poker.STRAIGHT_FLUSH),
        ("7h 7d 7c 7s 2h", poker.FOUR_OF_A_KIND),
        ("Kh Kd Kc 7s 7h", poker.FULL_HOUSE),
        ("Ah Kh 9h 5h 2h", poker.FLUSH),
        ("9h 8d 7c 6s 5h", poker.STRAIGHT),
        ("Ah 2d 3c 4s 5h", poker.STRAIGHT),
        ("Ah Ad Ac 5s 9h", poker.THREE_OF_A_KIND),
        ("Ah Ad Kc Ks 9h", poker.TWO_PAIR),
        ("Ah Ad Kc 9s 7h", poker.PAIR),
        ("Ah Kd Qc 9s 7h", poker.HIGH_CARD),
    ],
)
def test_categories(hand, category):
    assert evaluate(parse_hand(hand)).category == category


def test_picks_the_best_five_from_seven():
    rank = evaluate(parse_hand("As Ks Qs Js 10s 2h 3d"))
    assert rank.category == poker.STRAIGHT_FLUSH
    assert rank.describe() == "Royal Flush"
    assert len(rank.cards) == 5


def test_wheel_is_the_lowest_straight():
    assert compare(parse_hand("Ah 2d 3c 4s 5h"), parse_hand("2h 3d 4c 5s 6h")) == -1


def test_ace_high_straight_beats_king_high():
    assert compare(parse_hand("Ah Kd Qc Js 10h"), parse_hand("Kh Qd Jc 10s 9h")) == 1


def test_kickers_break_ties():
    assert compare(parse_hand("Ah Ad Kc 9s 7h"), parse_hand("As Ac Qd 9h 7s")) == 1
    assert compare(parse_hand("Ah Ad Kc 9s 7h"), parse_hand("As Ac Kd 9h 7s")) == 0


def test_flush_beats_a_straight():
    assert compare(parse_hand("2h 5h 9h Jh Kh"), parse_hand("9h 8d 7c 6s 5h")) == 1


def test_full_house_uses_the_best_trips_available():
    rank = evaluate(parse_hand("Kh Kd Kc 7s 7h 2d 2c"))
    assert rank.describe() == "Kings full of Sevens"


def test_two_pair_from_three_pairs_keeps_the_top_two():
    rank = evaluate(parse_hand("Ah Ad Kc Ks 9h 9d 3c"))
    assert rank.tiebreakers == (14, 13, 9)


def test_straight_flush_beats_four_of_a_kind():
    assert compare(parse_hand("9s 8s 7s 6s 5s"), parse_hand("7h 7d 7c 7s 2h")) == 1


def test_a_straight_and_a_flush_that_are_not_a_straight_flush():
    # Five spades plus a separate straight - the flush must win, not a phantom
    # straight flush built out of mixed suits.
    rank = evaluate(parse_hand("2s 4s 6s 8s 10s 3h 5d"))
    assert rank.category == poker.FLUSH


def test_packed_value_orders_identically_to_categories():
    hands = [
        "Ah Kd Qc 9s 7h", "Ah Ad Kc 9s 7h", "Ah Ad Kc Ks 9h", "Ah Ad Ac 5s 9h",
        "9h 8d 7c 6s 5h", "Ah Kh 9h 5h 2h", "Kh Kd Kc 7s 7h", "7h 7d 7c 7s 2h",
        "As Ks Qs Js 10s",
    ]
    values = [evaluate(parse_hand(hand)).value for hand in hands]
    assert values == sorted(values)


def test_too_few_cards_is_an_error():
    with pytest.raises(ValueError):
        evaluate(parse_hand("Ah Kd Qc"))


def test_describe_never_crashes_on_any_five_card_hand():
    from itertools import combinations
    from pysino.core.cards import full_deck

    deck = full_deck()[:14]
    for combo in combinations(deck, 5):
        assert evaluate(combo).describe()
