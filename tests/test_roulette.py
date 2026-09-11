import random

import pytest

from pysino.games import roulette as r


def test_wheel_has_37_unique_pockets():
    assert len(r.WHEEL_ORDER) == 37
    assert set(r.WHEEL_ORDER) == set(range(37))


def test_colours():
    assert r.colour_of(0) == "green"
    assert r.colour_of(1) == "red"
    assert r.colour_of(2) == "black"
    assert len(r.RED_NUMBERS) == len(r.BLACK_NUMBERS) == 18


@pytest.mark.parametrize(
    "covered,odds", [(1, 35), (2, 17), (3, 11), (4, 8), (6, 5), (12, 2), (18, 1)]
)
def test_standard_payout_odds(covered, odds):
    assert r.payout_odds(covered) == odds


@pytest.mark.parametrize("covered", [0, 5, 7, 37])
def test_non_standard_coverage_is_rejected(covered):
    with pytest.raises(ValueError):
        r.payout_odds(covered)


@pytest.mark.parametrize(
    "maker,args",
    [
        (r.straight, (17,)), (r.split, (1, 2)), (r.street, (1,)), (r.corner, (1,)),
        (r.six_line, (1,)), (r.column, (0,)), (r.dozen, (0,)), (r.red, ()),
        (r.black, ()), (r.odd, ()), (r.even, ()), (r.low, ()), (r.high, ()),
    ],
)
def test_every_bet_returns_36_of_37_on_average(maker, args):
    bet = maker(*args, 100)
    total = sum(bet.payout(number) for number in range(37))
    assert total / 37 / 100 == pytest.approx(36 / 37)


def test_zero_loses_every_outside_bet():
    for bet in (r.red(10), r.black(10), r.odd(10), r.even(10), r.low(10), r.high(10)):
        assert bet.payout(0) == 0


def test_straight_up_pays_36_times_the_stake():
    assert r.straight(17, 10).payout(17) == 360
    assert r.straight(17, 10).payout(18) == 0


def test_corner_covers_the_right_four_numbers():
    assert r.corner(1, 10).numbers == {1, 2, 4, 5}


def test_columns_partition_the_board():
    columns = [r.column(index, 1).numbers for index in range(3)]
    assert set().union(*columns) == set(range(1, 37))
    assert sum(len(column) for column in columns) == 36


def test_dozens_partition_the_board():
    dozens = [r.dozen(index, 1).numbers for index in range(3)]
    assert set().union(*dozens) == set(range(1, 37))


def test_settle_splits_winners_and_losers():
    game = r.RouletteGame(random.Random(0))
    bets = [r.red(10), r.black(10), r.straight(1, 10)]
    result = game.settle(bets, 1)
    assert result.colour == "red"
    assert result.total_staked == 30
    assert result.total_returned == 20 + 360
    assert len(result.winners) == 2
    assert len(result.losers) == 1


def test_history_is_capped():
    game = r.RouletteGame(random.Random(0))
    for _ in range(80):
        game.spin()
    assert len(game.history) <= 50


def test_hot_and_cold_reads_history():
    hot, cold = r.hot_and_cold([7, 7, 7, 3, 3, 12], count=2)
    assert hot[0] == 7
    assert len(cold) == 2


def test_simulated_house_edge_is_about_2_7_percent():
    game = r.RouletteGame(random.Random(4))
    staked = returned = 0
    for _ in range(60_000):
        result = game.play([r.red(10), r.straight(17, 10)])
        staked += result.total_staked
        returned += result.total_returned
    assert 0.94 < returned / staked < 1.01


def test_pocket_angles_cover_the_wheel_once():
    """Every pocket gets its own slice, and they wrap exactly once around."""
    import math

    angles = sorted(r.pocket_angle(number) for number in range(37))
    assert len(angles) == 37
    step = math.tau / 37
    gaps = [b - a for a, b in zip(angles, angles[1:])]
    assert all(abs(gap - step) < 1e-9 for gap in gaps)
    assert 0 < angles[0] < step
    assert angles[-1] < math.tau


def test_pocket_angle_follows_the_wheel():
    import math

    for number in (0, 17, 26):
        base = r.pocket_angle(number)
        assert r.pocket_angle(number, 1.25) == pytest.approx(base + 1.25)
        assert r.pocket_index(number) == r.WHEEL_ORDER.index(number)


def test_first_pocket_is_the_zero():
    assert r.pocket_index(0) == 0
