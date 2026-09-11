import random

import pytest

from pysino.games.mines import (
    MAX_MINES, State, TILE_COUNT, MinesGame, multiplier_for, multiplier_table,
    safe_probability,
)


def game_with_mines_at(positions, bet=100, mines=None):
    game = MinesGame(rng=random.Random(0))
    game.start(bet, mines or len(positions))
    game.mine_positions = set(positions)
    return game


@pytest.mark.parametrize("mines", [1, 3, 5, 10, 24])
@pytest.mark.parametrize("picks", [1, 2, 3])
def test_every_cash_out_point_has_the_same_expected_value(mines, picks):
    if picks > TILE_COUNT - mines:
        pytest.skip("more picks than safe tiles")
    expected = safe_probability(mines, picks) * multiplier_for(mines, picks)
    assert expected == pytest.approx(0.99)


def test_multipliers_increase_with_each_pick():
    table = multiplier_table(3)
    assert table == sorted(table)
    assert all(b > a for a, b in zip(table, table[1:]))


def test_more_mines_pay_more_for_the_same_picks():
    assert multiplier_for(10, 1) > multiplier_for(3, 1)


def test_a_single_pick_with_24_mines_pays_about_25x():
    assert multiplier_for(24, 1) == pytest.approx(24.75)


def test_revealing_a_safe_tile_raises_the_multiplier():
    game = game_with_mines_at([24], bet=100, mines=1)
    assert game.reveal(0) is True
    assert game.picks == 1
    assert game.multiplier > 1.0


def test_hitting_a_mine_busts_the_board():
    game = game_with_mines_at([5], bet=100, mines=1)
    assert game.reveal(5) is False
    assert game.state is State.BUSTED
    assert game.hit_position == 5


def test_cash_out_pays_the_current_multiplier():
    game = game_with_mines_at([24], bet=100, mines=1)
    game.reveal(0)
    payout = game.cash_out()
    assert game.state is State.CASHED
    assert payout == int(100 * multiplier_for(1, 1))


def test_cannot_cash_out_before_revealing_anything():
    game = game_with_mines_at([24], bet=100, mines=1)
    with pytest.raises(RuntimeError):
        game.cash_out()


def test_cannot_reveal_the_same_tile_twice():
    game = game_with_mines_at([24], bet=100, mines=1)
    game.reveal(0)
    with pytest.raises(ValueError):
        game.reveal(0)


def test_cannot_reveal_off_the_board():
    game = game_with_mines_at([24], bet=100, mines=1)
    with pytest.raises(ValueError):
        game.reveal(TILE_COUNT)


def test_cannot_play_a_busted_board():
    game = game_with_mines_at([5], bet=100, mines=1)
    game.reveal(5)
    with pytest.raises(RuntimeError):
        game.reveal(6)


def test_clearing_the_board_cashes_out_automatically():
    game = game_with_mines_at([24], bet=100, mines=1)
    for position in range(24):
        game.reveal(position)
    assert game.is_cleared
    assert game.state is State.CASHED
    assert game.payout == int(100 * multiplier_for(1, 24))


@pytest.mark.parametrize("mines", [0, MAX_MINES + 1, -1])
def test_invalid_mine_counts_are_rejected(mines):
    game = MinesGame(rng=random.Random(0))
    with pytest.raises(ValueError):
        game.start(100, mines)


def test_invalid_bet_is_rejected():
    game = MinesGame(rng=random.Random(0))
    with pytest.raises(ValueError):
        game.start(0, 3)


def test_mines_are_placed_without_duplicates(rng):
    game = MinesGame(rng=rng)
    for mines in (1, 5, 12, 24):
        game.start(10, mines)
        assert len(game.mine_positions) == mines
        assert all(0 <= position < TILE_COUNT for position in game.mine_positions)


def test_long_run_returns_about_ninety_nine_percent():
    """Always cashing out after three picks should return close to the edge."""
    rng = random.Random(99)
    game = MinesGame(rng=rng)
    staked = returned = 0
    for _ in range(20_000):
        game.start(100, 3)
        staked += 100
        for _ in range(3):
            spot = next(i for i in range(TILE_COUNT) if i not in game.revealed)
            if not game.reveal(spot):
                break
        if game.state is State.PLAYING:
            returned += game.cash_out()
    assert 0.95 < returned / staked < 1.03
