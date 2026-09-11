import random

import pytest

from pysino.games.crash import (
    CrashGame, State, draw_crash_point, multiplier_at, time_for_multiplier,
)


def test_crash_points_are_never_below_one():
    rng = random.Random(5)
    assert all(draw_crash_point(rng) >= 1.0 for _ in range(5_000))


@pytest.mark.parametrize("target", [1.5, 2.0, 5.0, 10.0])
def test_every_cash_out_target_returns_about_ninety_nine_percent(target):
    rng = random.Random(2024)
    trials = 120_000
    won = sum(target for _ in range(trials) if draw_crash_point(rng) >= target)
    assert 0.95 < won / trials < 1.03


def test_instant_busts_are_roughly_the_house_edge():
    rng = random.Random(11)
    trials = 100_000
    busts = sum(1 for _ in range(trials) if draw_crash_point(rng) == 1.0)
    # Rounding down to two decimals folds the 1.00-1.01 band in here too.
    assert 0.01 < busts / trials < 0.03


def test_multiplier_grows_over_time():
    assert multiplier_at(0) == 1.0
    assert multiplier_at(1) > multiplier_at(0.5) > 1.0


def test_time_for_multiplier_inverts_the_curve():
    for target in (1.5, 2.0, 10.0):
        assert multiplier_at(time_for_multiplier(target)) == pytest.approx(target, rel=1e-3)


def test_cash_out_before_the_crash_pays():
    game = CrashGame(rng=random.Random(0))
    game.crash_point = 5.0
    game.state = State.RUNNING
    game.bet = 100
    game.elapsed = time_for_multiplier(2.0)
    payout = game.cash_out()
    assert game.state is State.CASHED
    assert payout == pytest.approx(200, abs=2)


def test_running_past_the_crash_point_busts():
    game = CrashGame(rng=random.Random(0))
    game.bet = 100
    game.crash_point = 2.0
    game.state = State.RUNNING
    game.tick(time_for_multiplier(3.0))
    assert game.state is State.CRASHED
    assert game.payout == 0


def test_auto_cash_out_fires_at_the_target():
    game = CrashGame(rng=random.Random(0))
    game.bet = 100
    game.crash_point = 10.0
    game.auto_cash_out = 2.0
    game.state = State.RUNNING
    game.tick(time_for_multiplier(2.5))
    assert game.state is State.CASHED
    assert game.cashed_at == 2.0
    assert game.payout == 200


def test_auto_cash_out_above_the_crash_point_never_fires():
    game = CrashGame(rng=random.Random(0))
    game.bet = 100
    game.crash_point = 2.0
    game.auto_cash_out = 5.0
    game.state = State.RUNNING
    game.tick(time_for_multiplier(6.0))
    assert game.state is State.CRASHED


def test_cannot_cash_out_twice():
    game = CrashGame(rng=random.Random(0))
    game.bet = 100
    game.crash_point = 5.0
    game.state = State.RUNNING
    game.elapsed = time_for_multiplier(2.0)
    game.cash_out()
    with pytest.raises(RuntimeError):
        game.cash_out()


def test_invalid_bet_is_rejected():
    game = CrashGame(rng=random.Random(0))
    with pytest.raises(ValueError):
        game.start(0)
