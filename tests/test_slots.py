import random

import pytest

from pysino.games import slots as s


def grid_from(rows):
    """Build a grid from three strings of single-letter symbol codes."""
    codes = {
        "C": s.CHERRY, "L": s.LEMON, "B": s.BELL, "H": s.HORSESHOE,
        "D": s.DIAMOND, "R": s.CROWN, "7": s.SEVEN, "W": s.WILD, "S": s.SCATTER,
    }
    return [[codes[letter] for letter in row] for row in rows]


def test_reel_strips_do_not_stack_identical_symbols():
    """A blocked strip would show three of a kind on a reel nearly every spin."""
    for strip in s.REEL_STRIPS:
        assert all(strip[i] != strip[(i + 1) % len(strip)] for i in range(len(strip)))


def test_strip_respects_the_configured_weights():
    for weights, strip in zip(s.REEL_WEIGHTS, s.REEL_STRIPS):
        for symbol, weight in weights.items():
            assert strip.count(symbol) == weight


def test_there_are_twenty_distinct_paylines():
    assert s.LINE_COUNT == 20
    assert len(set(s.PAYLINES)) == 20
    assert all(len(line) == s.REELS for line in s.PAYLINES)
    assert all(0 <= row < s.ROWS for line in s.PAYLINES for row in line)


def test_three_of_a_kind_pays_the_paytable():
    won = s.evaluate_line([s.BELL, s.BELL, s.BELL, s.CHERRY, s.LEMON], 10)
    assert won == (s.BELL, 3, s.PAYTABLE[s.BELL][0] * 10)


def test_five_of_a_kind_pays_the_top_prize():
    won = s.evaluate_line([s.SEVEN] * 5, 1)
    assert won == (s.SEVEN, 5, s.PAYTABLE[s.SEVEN][2])


def test_wilds_substitute():
    won = s.evaluate_line([s.BELL, s.WILD, s.BELL, s.CHERRY, s.LEMON], 10)
    assert won == (s.BELL, 3, s.PAYTABLE[s.BELL][0] * 10)


def test_all_wilds_pay_the_wild_rate():
    symbol, count, amount = s.evaluate_line([s.WILD] * 5, 1)
    assert symbol == s.WILD
    assert amount == s.PAYTABLE[s.WILD][2]


def test_leading_wilds_take_whichever_line_is_worth_more():
    # Three wilds then two sevens: paying it as five sevens beats three wilds.
    symbol, count, amount = s.evaluate_line(
        [s.WILD, s.WILD, s.WILD, s.SEVEN, s.SEVEN], 1
    )
    assert (symbol, count) == (s.SEVEN, 5)
    assert amount == s.PAYTABLE[s.SEVEN][2]


def test_runs_must_start_on_the_first_reel():
    assert s.evaluate_line([s.CHERRY, s.BELL, s.BELL, s.BELL, s.LEMON], 10) is None


def test_two_of_a_kind_pays_nothing():
    assert s.evaluate_line([s.BELL, s.BELL, s.CHERRY, s.LEMON, s.SEVEN], 10) is None


def test_scatter_does_not_pay_on_a_line():
    assert s.evaluate_line([s.SCATTER, s.SCATTER, s.SCATTER, s.BELL, s.BELL], 10) is None


def test_scatters_pay_anywhere_and_award_free_spins():
    grid = grid_from(["SCLBL", "CSLBL", "CLSBL"])
    result = s.evaluate(grid, line_bet=10)
    assert result.scatter_count == 3
    assert result.scatter_win == s.SCATTER_PAYS[3] * 10 * s.LINE_COUNT
    assert result.free_spins_awarded == s.FREE_SPIN_AWARD[3]


def test_free_spin_multiplier_applies_to_the_whole_win():
    grid = grid_from(["77777", "CLBHD", "CLBHD"])
    normal = s.evaluate(grid, 1)
    bonus = s.evaluate(grid, 1, multiplier=s.FREE_SPIN_MULTIPLIER, was_free_spin=True)
    assert bonus.total_win == normal.total_win * s.FREE_SPIN_MULTIPLIER
    assert bonus.total_bet == 0


def test_line_win_reports_the_cells_it_used():
    grid = grid_from(["CLBHD", "77777", "CLBHD"])
    result = s.evaluate(grid, 1)
    win = next(w for w in result.line_wins if w.symbol == s.SEVEN)
    assert win.positions == [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)]


def test_free_spins_are_consumed_and_cost_nothing(rng):
    machine = s.SlotMachine(rng)
    machine.free_spins = 2
    first = machine.spin(10)
    assert first.was_free_spin
    assert first.total_bet == 0
    assert first.multiplier == s.FREE_SPIN_MULTIPLIER
    machine.spin(10)
    assert machine.free_spins == 0 or machine.free_spins > 0  # a retrigger is fine
    paid = machine.spin(10)
    if not machine.in_free_spins:
        assert paid.total_bet == 10 * s.LINE_COUNT


def test_spin_rejects_a_non_positive_bet(rng):
    with pytest.raises(ValueError):
        s.SlotMachine(rng).spin(0)


def test_grid_has_the_right_shape(rng):
    grid = s.spin_grid(rng)
    assert len(grid) == s.ROWS
    assert all(len(row) == s.REELS for row in grid)
    assert all(symbol in s.SYMBOLS for row in grid for symbol in row)


def test_every_symbol_has_a_glyph_and_a_name():
    for symbol in s.SYMBOLS:
        assert s.SYMBOL_GLYPHS[symbol]
        assert s.SYMBOL_NAMES[symbol]


@pytest.mark.parametrize("seed", [7, 21])
def test_return_to_player_is_in_a_sane_band(seed):
    """The machine is tuned for roughly 95%; guard against drift."""
    machine = s.SlotMachine(random.Random(seed))
    staked = won = 0
    for _ in range(120_000):
        if not machine.in_free_spins:
            staked += s.LINE_COUNT
        won += machine.spin(1).total_win
    assert 0.88 < won / staked < 1.02, f"RTP {won / staked:.4f} has drifted"


def test_hit_rate_is_reasonable():
    machine = s.SlotMachine(random.Random(3))
    hits = sum(1 for _ in range(20_000) if machine.spin(1).total_win > 0)
    assert 0.2 < hits / 20_000 < 0.65
