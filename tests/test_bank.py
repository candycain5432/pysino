import pytest

from pysino import config
from pysino.core.bank import Bank, GameStats, InsufficientChips


def test_starts_with_the_configured_stack():
    assert Bank().chips == config.STARTING_CHIPS


def test_wager_and_award_move_chips():
    bank = Bank(1_000)
    bank.wager("slots", 100)
    assert bank.chips == 900
    bank.award("slots", 250)
    assert bank.chips == 1_150


def test_cannot_wager_more_than_the_stack():
    bank = Bank(50)
    with pytest.raises(InsufficientChips):
        bank.wager("slots", 51)
    assert bank.chips == 50


def test_negative_amounts_are_rejected():
    bank = Bank(100)
    with pytest.raises(ValueError):
        bank.wager("slots", -1)
    with pytest.raises(ValueError):
        bank.award("slots", -1)


def test_chips_carry_between_games():
    bank = Bank(500)
    bank.wager("blackjack", 100)
    bank.award("blackjack", 200)
    bank.wager("roulette", 600)
    assert bank.chips == 0
    assert bank.stats_for("blackjack").wagered == 100
    assert bank.stats_for("roulette").wagered == 600


def test_finish_round_records_outcomes():
    bank = Bank(1_000)
    assert bank.finish_round("slots", 100, 300) == 200
    assert bank.stats_for("slots").wins == 1
    assert bank.finish_round("slots", 100, 0) == -100
    assert bank.stats_for("slots").losses == 1
    assert bank.finish_round("slots", 100, 100) == 0
    assert bank.stats_for("slots").pushes == 1
    assert bank.stats_for("slots").rounds == 3


def test_streaks_track_wins_and_losses():
    bank = Bank(10_000)
    for _ in range(3):
        bank.finish_round("slots", 10, 20)
    assert bank.stats_for("slots").current_streak == 3
    assert bank.stats_for("slots").best_streak == 3
    bank.finish_round("slots", 10, 0)
    assert bank.stats_for("slots").current_streak == -1
    assert bank.stats_for("slots").best_streak == 3


def test_biggest_win_tracks_net_not_gross():
    bank = Bank(10_000)
    bank.finish_round("slots", 100, 500)
    assert bank.stats_for("slots").biggest_win == 400


def test_rtp_and_win_rate():
    stats = GameStats(wagered=1_000, returned=950, wins=4, losses=6)
    assert stats.rtp == pytest.approx(0.95)
    assert stats.win_rate == pytest.approx(0.4)
    assert stats.net == -50


def test_empty_stats_do_not_divide_by_zero():
    stats = GameStats()
    assert stats.rtp == 0.0
    assert stats.win_rate == 0.0


def test_save_and_load_round_trip(tmp_path):
    bank = Bank(1_234)
    bank.wager("mines", 34)
    bank.unlock("first_win")
    path = bank.save()
    restored = Bank.load(path)
    assert restored.chips == 1_200
    assert restored.stats_for("mines").wagered == 34
    assert "first_win" in restored.achievements


def test_loading_a_missing_file_gives_a_fresh_bank(tmp_path):
    assert Bank.load(tmp_path / "nope.json").chips == config.STARTING_CHIPS


def test_loading_a_corrupt_file_gives_a_fresh_bank(tmp_path):
    broken = tmp_path / "profile.json"
    broken.write_text("{not json at all")
    assert Bank.load(broken).chips == config.STARTING_CHIPS


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    bank = Bank()
    path = bank.save()
    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))


def test_daily_bonus_is_once_per_day():
    bank = Bank(0)
    assert bank.claim_daily_bonus() == config.DAILY_BONUS_CHIPS
    assert bank.claim_daily_bonus() == 0


def test_bailout_only_when_broke():
    bank = Bank(config.BAILOUT_THRESHOLD)
    assert bank.claim_bailout() == config.BAILOUT_CHIPS
    assert Bank(10_000).claim_bailout() == 0


def test_achievements_unlock_once():
    bank = Bank()
    assert bank.unlock("first_win") is True
    assert bank.unlock("first_win") is False
    assert bank.unlock("not_a_real_achievement") is False


def test_high_roller_unlocks_on_a_big_bet():
    bank = Bank(10_000)
    bank.wager("roulette", 5_000)
    assert "high_roller" in bank.achievements


def test_subscribers_are_notified():
    bank = Bank(100)
    seen = []
    unsubscribe = bank.subscribe(lambda reason, delta: seen.append((reason, delta)))
    bank.wager("slots", 10)
    bank.award("slots", 30)
    assert seen == [("wager", -10), ("award", 30)]
    unsubscribe()
    bank.wager("slots", 10)
    assert len(seen) == 2


def test_peak_chips_tracks_the_high_water_mark():
    bank = Bank(100)
    bank.award("slots", 900)
    bank.wager("slots", 500)
    assert bank.peak_chips == 1_000


def test_balance_history_stays_bounded():
    bank = Bank(1_000_000)
    for _ in range(1_200):
        bank.finish_round("slots", 1, 1)
    assert len(bank.balance_history) <= 500
