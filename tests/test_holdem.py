import random

import pytest

from pysino.core.cards import parse_hand
from pysino.games.holdem import (
    Action, AIProfile, HoldemGame, Player, Street, build_pots, estimate_equity,
    make_table,
)


def seat(name, chips, **kwargs):
    return Player(name=name, chips=chips, seat=kwargs.pop("seat", 0), **kwargs)


def table(stacks, small=10, big=20, seed=0):
    players = [seat(f"P{i}", chips, seat=i) for i, chips in enumerate(stacks)]
    return HoldemGame(random.Random(seed), players, small, big), players


# ------------------------------------------------------------- side pots --
def test_side_pots_layer_by_commitment():
    short, mid, big = seat("Short", 0), seat("Mid", 0), seat("Big", 0)
    short.committed, mid.committed, big.committed = 50, 500, 800
    pots = build_pots([short, mid, big])
    assert [pot.amount for pot in pots] == [150, 900, 300]
    assert [len(pot.eligible) for pot in pots] == [3, 2, 1]
    assert sum(pot.amount for pot in pots) == 1_350


def test_folded_players_fund_the_pot_but_cannot_win_it():
    folder, live = seat("Folder", 0), seat("Live", 0)
    folder.committed, folder.folded = 100, True
    live.committed = 100
    pots = build_pots([folder, live])
    assert sum(pot.amount for pot in pots) == 200
    assert all(folder not in pot.eligible for pot in pots)


def test_equal_eligibility_layers_are_merged():
    """A player folding their blind must not look like a side pot."""
    small, big, utg = seat("SB", 0), seat("BB", 0), seat("UTG", 0)
    small.committed, small.folded = 10, True
    big.committed, utg.committed = 20, 20
    pots = build_pots([small, big, utg])
    assert len(pots) == 1
    assert pots[0].amount == 50


def test_no_contributions_means_no_pots():
    assert build_pots([seat("A", 100), seat("B", 100)]) == []


# ---------------------------------------------------------------- blinds --
def test_heads_up_button_posts_the_small_blind_and_acts_first():
    game, players = table([1_000, 1_000])
    game.start_hand()
    button = players[game.button]
    assert button.committed == game.small_blind
    assert game.current_player is button


def test_three_handed_blinds_sit_left_of_the_button():
    game, players = table([1_000, 1_000, 1_000])
    game.start_hand()
    order = game.seated
    button_index = order.index(players[game.button])
    small = order[(button_index + 1) % 3]
    big = order[(button_index + 2) % 3]
    assert small.committed == game.small_blind
    assert big.committed == game.big_blind
    # Under the gun acts first preflop.
    assert game.current_player is order[button_index]


def test_everyone_gets_two_cards():
    game, players = table([1_000] * 4)
    game.start_hand()
    assert all(len(player.hole) == 2 for player in players)
    dealt = [card for player in players for card in player.hole]
    assert len(set(dealt)) == 8


def test_a_short_stack_posts_what_it_has_and_is_all_in():
    game, players = table([1_000, 5])
    game.start_hand()
    short = next(player for player in players if player.chips == 0)
    assert short.all_in
    assert short.committed == 5


# --------------------------------------------------------------- betting --
def test_big_blind_gets_the_option_to_raise():
    game, players = table([1_000] * 3)
    game.start_hand()
    order = game.seated
    big = order[(order.index(players[game.button]) + 2) % 3]
    game.act(Action.CALL)
    game.act(Action.CALL)
    assert game.current_player is big
    assert Action.CHECK in game.legal_actions()
    assert Action.RAISE in game.legal_actions()


def test_checking_through_advances_the_street():
    game, players = table([1_000] * 3)
    game.start_hand()
    game.act(Action.CALL)
    game.act(Action.CALL)
    game.act(Action.CHECK)
    assert game.street is Street.FLOP
    assert len(game.board) == 3


def test_folding_down_to_one_player_ends_the_hand():
    game, players = table([1_000] * 3)
    game.start_hand()
    game.act(Action.FOLD)
    game.act(Action.FOLD)
    assert game.is_hand_over
    assert not game.result.went_to_showdown
    assert len(game.result.winners) == 1
    assert game.result.winners[0].chips > 1_000


def test_a_raise_reopens_action_for_players_who_already_acted():
    game, players = table([1_000] * 3)
    game.start_hand()
    first = game.current_player
    game.act(Action.CALL)
    game.act(Action.RAISE, 60)
    assert not first.has_acted
    assert game.current_bet == 60


def test_minimum_raise_tracks_the_last_raise_size():
    game, players = table([1_000] * 3)
    game.start_hand()
    game.act(Action.RAISE, 60)          # raise of 40 over the big blind
    assert game.min_raise == 40
    assert game.min_raise_to(game.current_player) == 100


def test_raise_below_the_minimum_is_lifted_to_it():
    game, players = table([1_000] * 3)
    game.start_hand()
    game.act(Action.RAISE, 25)          # illegal size, clamped up
    assert game.current_bet == 40


def test_raise_above_the_stack_is_capped_at_all_in():
    game, players = table([1_000, 1_000, 200])
    game.start_hand()
    player = game.current_player
    game.act(Action.RAISE, 10_000)
    assert player.chips == 0
    assert player.all_in


def test_illegal_action_is_refused():
    game, players = table([1_000] * 3)
    game.start_hand()
    with pytest.raises(RuntimeError):
        game.act(Action.CHECK)          # there is a blind to call


def test_cannot_raise_when_everyone_else_is_all_in():
    game, players = table([1_000, 30, 30])
    game.start_hand()
    while not game.is_hand_over and game.current_player:
        actions = game.legal_actions()
        others = [p for p in game.contenders if p is not game.current_player and not p.all_in]
        if not others:
            assert Action.RAISE not in actions and Action.BET not in actions
            break
        game.act(Action.CALL if Action.CALL in actions else Action.CHECK)


def test_all_in_players_are_skipped():
    game, players = table([1_000, 1_000, 40])
    game.start_hand()
    for _ in range(12):
        if game.is_hand_over:
            break
        current = game.current_player
        assert current is None or not current.all_in
        if current is None:
            break
        actions = game.legal_actions()
        game.act(Action.CALL if Action.CALL in actions else Action.CHECK)


# -------------------------------------------------------------- showdown --
def test_split_pot_divides_evenly():
    game, players = table([1_000, 1_000])
    game.start_hand()
    players[0].hole = parse_hand("Ah Kh")
    players[1].hole = parse_hand("Ad Kd")
    game.board = parse_hand("2c 5s 9d Jh 3c")
    game.street = Street.RIVER
    for player in players:
        player.committed = 100
        player.chips = 900
        player.bet = 0
    game._showdown()
    assert players[0].chips == players[1].chips == 1_000


def test_odd_chip_goes_to_a_single_winner():
    game, players = table([1_000, 1_000])
    game.start_hand()
    players[0].hole = parse_hand("Ah Kh")
    players[1].hole = parse_hand("Ad Kd")
    game.board = parse_hand("2c 5s 9d Jh 3c")
    for player in players:
        player.committed = 101
        player.chips = 899
        player.bet = 0
    game._showdown()
    assert sum(player.chips for player in players) == 2_000


def test_best_hand_takes_the_pot():
    game, players = table([1_000, 1_000])
    game.start_hand()
    players[0].hole = parse_hand("Ah As")
    players[1].hole = parse_hand("2c 7d")
    game.board = parse_hand("Ad Kh 9s 4c 3h")
    for player in players:
        player.committed = 200
        player.chips = 800
        player.bet = 0
    game._showdown()
    assert players[0].chips == 1_200
    assert players[1].chips == 800


def test_short_stack_can_only_win_the_main_pot():
    game, players = table([1_000, 1_000, 1_000])
    game.start_hand()
    short, mid, big = players
    short.hole = parse_hand("Ah As")     # best hand, but only 100 committed
    mid.hole = parse_hand("Kh Ks")
    big.hole = parse_hand("Qh Qs")
    game.board = parse_hand("2c 5d 9h Jc 3s")
    for player in players:
        player.chips, player.bet, player.folded = 0, 0, False
    short.committed, mid.committed, big.committed = 100, 400, 400
    game.street = Street.RIVER
    game._showdown()
    assert short.chips == 300            # main pot only: 100 x 3
    assert mid.chips == 600              # side pot: 300 x 2
    assert big.chips == 0


# ------------------------------------------------------------------ bots --
def test_equity_of_the_nuts_is_total():
    equity = estimate_equity(
        parse_hand("Ah Kh"), parse_hand("Qh Jh 10h 2c 3d"), 1, random.Random(0), 200
    )
    assert equity == 1.0


def test_equity_of_the_worst_hand_is_low():
    equity = estimate_equity(
        parse_hand("2c 7d"), parse_hand("Ah Kh Qh Jh 9s"), 3, random.Random(0), 300
    )
    assert equity < 0.25


def test_aces_beat_a_random_hand_most_of_the_time():
    equity = estimate_equity(parse_hand("Ah As"), [], 1, random.Random(3), 600)
    assert 0.78 < equity < 0.92


def test_bots_only_pick_legal_actions():
    game, players = table([2_000] * 4, seed=5)
    for player in players:
        player.profile = AIProfile("Test", iterations=40)
    for _ in range(30):
        game.start_hand()
        while not game.is_hand_over:
            action, amount = game.ai_decision()
            assert action in game.legal_actions()
            game.act(action, amount)


def test_make_table_seats_a_human_and_bots(rng):
    players = make_table(rng, human_stack=1_000, bot_count=3)
    assert len(players) == 4
    assert players[0].is_human
    assert all(player.profile for player in players[1:])


# ------------------------------------------------------------ invariants --
def test_chips_are_conserved_across_many_hands():
    game, players = table([2_000] * 5, seed=42)
    for player in players:
        player.profile = AIProfile("Test", iterations=40)
    start = sum(player.chips for player in players)
    hands = 0
    for _ in range(200):
        if len([p for p in players if p.chips > 0]) < 2:
            break
        game.start_hand()
        guard = 0
        while not game.is_hand_over:
            guard += 1
            assert guard < 300, "betting round failed to terminate"
            game.play_ai_turn()
        hands += 1
        assert sum(player.chips for player in players) == start
        assert all(player.chips >= 0 for player in players)
    assert hands > 5


def test_pot_always_matches_what_players_committed():
    game, players = table([2_000] * 3, seed=9)
    for player in players:
        player.profile = AIProfile("Test", iterations=30)
    for _ in range(25):
        game.start_hand()
        while not game.is_hand_over:
            assert game.pot == sum(player.committed for player in players)
            game.play_ai_turn()


def test_a_table_needs_two_players():
    with pytest.raises(ValueError):
        HoldemGame(random.Random(0), [seat("Solo", 100)])
