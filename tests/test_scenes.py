"""Headless smoke tests for the pygame layer.

These drive real interactions against a dummy video driver.  They are not
pixel tests - they exist so that a crash in any scene fails the suite rather
than the player's session.
"""

import os

import pytest

pygame = pytest.importorskip("pygame")

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture
def app():
    from pysino.app import App

    application = App(headless=True)
    application.bank.chips = 50_000
    application.chip_ticker.set(50_000, immediate=True)
    yield application
    pygame.quit()


def advance(application, frames=1, dt=1 / 60):
    for _ in range(frames):
        application.step(dt)


def press(application, key):
    application.scenes.current.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": key, "unicode": "", "mod": 0})
    )


def click(application, position, button=1):
    scene = application.scenes.current
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        scene.handle_event(pygame.event.Event(kind, {"pos": position, "button": button}))


# --------------------------------------------------------------- the shell --
def test_every_registered_scene_opens_and_draws(app):
    for name in app.scene_names:
        app.go_to(name, instant=True)
        advance(app, 12)
        assert app.scenes.current is not None


def test_canvas_is_the_declared_size(app):
    from pysino import config

    assert app.canvas.get_size() == config.BASE_SIZE


def test_window_coordinates_map_into_canvas_space(app):
    app._scale = 0.5
    app._offset = (100, 40)
    assert app.to_canvas((100, 40)) == (0, 0)
    assert app.to_canvas((740, 400)) == (1280, 720)


def test_escape_returns_to_the_lobby(app):
    app.go_to("blackjack", instant=True)
    advance(app, 2)
    press(app, pygame.K_ESCAPE)
    advance(app, 40)
    assert app.scenes.current.title == "Lobby"


def test_lobby_number_keys_open_each_game(app):
    from pysino.scenes.lobby import GAMES

    for index, entry in enumerate(GAMES):
        app.go_to("lobby", instant=True)
        advance(app, 2)
        press(app, pygame.K_1 + index)
        advance(app, 40)
        assert app.scenes.current is not None


# ------------------------------------------------------------ the games --
def test_blackjack_plays_a_hand(app):
    from pysino.games.blackjack import State

    app.go_to("blackjack", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    press(app, pygame.K_SPACE)
    advance(app, 30)
    if scene.game.state is State.INSURANCE:
        scene._decline_insurance()
    guard = 0
    while scene.game.state is State.PLAYER and guard < 30:
        guard += 1
        press(app, pygame.K_s)          # stand
        advance(app, 20)
    advance(app, 90)
    assert scene.game.state is State.DONE
    assert scene.game.result is not None


def test_slots_spin_resolves(app):
    app.go_to("slots", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    before = app.bank.chips
    press(app, pygame.K_SPACE)
    advance(app, 200)
    assert not scene.spinning
    assert scene.result is not None
    assert app.bank.chips != before or scene.result.total_win == scene.result.total_bet


def test_mines_reveal_and_cash_out(app):
    from pysino.games.mines import State, TILE_COUNT

    app.go_to("mines", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    press(app, pygame.K_SPACE)
    advance(app, 4)
    assert scene.game.state is State.PLAYING

    safe = next(i for i in range(TILE_COUNT) if i not in scene.game.mine_positions)
    click(app, scene._tile_rect(safe).center)
    advance(app, 6)
    assert scene.game.picks == 1

    before = app.bank.chips
    press(app, pygame.K_c)
    advance(app, 6)
    assert scene.game.state is State.CASHED
    assert app.bank.chips > before


def test_roulette_places_bets_and_spins(app):
    app.go_to("roulette", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    click(app, scene._spot_by_key["red"].rect.center)
    click(app, scene._spot_by_key["straight-17"].rect.center)
    assert scene.total_staked > 0
    advance(app, 2)          # the spin button enables on the next frame
    press(app, pygame.K_SPACE)
    advance(app, 300)
    assert not scene.spinning
    assert scene.winning_number in range(37)
    assert scene.bets == {}


def test_roulette_right_click_clears_a_spot(app):
    app.go_to("roulette", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    spot = scene._spot_by_key["red"]
    click(app, spot.rect.center)
    assert scene.bets
    click(app, spot.rect.center, button=3)
    assert scene.bets == {}


def test_crash_launches_and_cashes_out(app):
    from pysino.games.crash import State

    app.go_to("crash", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    scene._launch()
    scene.game.crash_point = 50.0          # keep the round alive long enough
    advance(app, 40)
    assert scene.game.state is State.RUNNING
    before = app.bank.chips
    scene._cash_out()
    advance(app, 4)
    assert scene.game.state is State.CASHED
    assert app.bank.chips > before


def test_video_poker_deals_and_draws(app):
    from pysino.games.videopoker import State

    app.go_to("videopoker", instant=True)
    advance(app, 2)
    scene = app.scenes.current
    press(app, pygame.K_SPACE)
    advance(app, 30)
    assert scene.game.state is State.HOLDING
    press(app, pygame.K_1)
    assert scene.game.held[0]
    press(app, pygame.K_SPACE)
    advance(app, 10)
    assert scene.game.state is State.COMPLETE


def _finish_live_hand(app):
    """Play whatever hand is in progress to the end, taking the passive line."""
    from pysino.games.holdem import Action

    scene = app.scenes.current
    guard = 0
    while not scene.game.is_hand_over and guard < 900:
        guard += 1
        if scene._is_human_turn:
            actions = scene.game.legal_actions(scene.human)
            scene._act(Action.CHECK if Action.CHECK in actions else Action.CALL)
        advance(app, 2)
    assert scene.game.is_hand_over
    advance(app, 40)


def _play_measured_hand(app):
    """Deal and play one hand, reading the bank from before the blinds go in.

    The scene posts blinds inside ``_start_hand``, so the balance has to be
    captured before that or a hand where the player is in the blinds looks
    like it lost chips twice.
    """
    scene = app.scenes.current
    _finish_live_hand(app)
    before = app.bank.chips
    scene._start_hand()
    advance(app, 6)
    _finish_live_hand(app)
    return before, scene.human.committed, scene.human.won_last


def test_holdem_plays_a_hand(app):
    app.go_to("holdem", instant=True)
    advance(app, 10)
    assert not app.scenes.current.game.is_hand_over
    _finish_live_hand(app)
    assert app.bank.chips >= 0


def test_holdem_bank_matches_what_was_staked_and_won(app):
    """The bank must move by exactly (won - staked): no chips minted."""
    app.go_to("holdem", instant=True)
    advance(app, 10)
    before, staked, won = _play_measured_hand(app)
    assert staked > 0
    assert app.bank.chips == before - staked + won


def test_holdem_chips_are_conserved_over_several_hands(app):
    app.go_to("holdem", instant=True)
    advance(app, 10)
    for _ in range(5):
        before, staked, won = _play_measured_hand(app)
        assert app.bank.chips == before - staked + won


def test_leaving_holdem_mid_hand_does_not_refund_the_pot(app):
    app.go_to("holdem", instant=True)
    advance(app, 20)
    scene = app.scenes.current
    during = app.bank.chips
    scene.on_exit()
    assert app.bank.chips == during


# --------------------------------------------------------- the whole point --
def test_chips_carry_between_games(app):
    """The headline feature: one stack, every table."""
    app.bank.chips = 10_000

    app.go_to("slots", instant=True)
    advance(app, 2)
    press(app, pygame.K_SPACE)
    advance(app, 200)
    after_slots = app.bank.chips
    assert after_slots != 10_000

    app.go_to("mines", instant=True)
    advance(app, 2)
    assert app.bank.chips == after_slots      # the stack followed the player

    press(app, pygame.K_SPACE)
    advance(app, 4)
    assert app.bank.chips == after_slots - app.scenes.current.staked


def test_profile_survives_a_save_and_reload(app, tmp_path):
    from pysino.core.bank import Bank

    app.go_to("slots", instant=True)
    advance(app, 2)
    press(app, pygame.K_SPACE)
    advance(app, 200)
    app.save()

    reloaded = Bank.load()
    assert reloaded.chips == app.bank.chips
    assert reloaded.stats_for("slots").rounds == app.bank.stats_for("slots").rounds


def test_bailout_restakes_a_broke_player(app):
    from pysino import config

    app.bank.chips = 0
    app.go_to("blackjack", instant=True)
    advance(app, 4)
    scene = app.scenes.current
    assert scene.is_broke
    scene.draw_bailout_prompt(app.canvas)
    scene._bailout()
    assert app.bank.chips == config.BAILOUT_CHIPS
