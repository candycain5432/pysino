import hashlib

import pytest

from pysino.core.rng import ProvablyFairRandom, commitment, replay


def test_stream_is_reproducible_from_the_seed_triple():
    first = ProvablyFairRandom("a" * 64, "client", 3)
    values = [first.random() for _ in range(20)]
    again = replay("a" * 64, "client", 3)
    assert [again.random() for _ in range(20)] == values


def test_different_nonces_give_different_streams():
    a = ProvablyFairRandom("a" * 64, "client", 1).random()
    b = ProvablyFairRandom("a" * 64, "client", 2).random()
    assert a != b


def test_commitment_matches_sha256_of_the_server_seed():
    generator = ProvablyFairRandom("deadbeef", "client")
    assert generator.commitment == hashlib.sha256(b"deadbeef").hexdigest()


def test_rotating_reveals_a_verifiable_seed_and_starts_a_new_one():
    generator = ProvablyFairRandom("a" * 64, "client", 5)
    reveal = generator.rotate_server_seed()
    assert reveal.verify()
    assert reveal.server_seed == "a" * 64
    assert reveal.rounds == 5
    assert generator.server_seed != "a" * 64
    assert generator.nonce == 0


def test_reveal_that_does_not_match_its_commitment_fails_verification():
    generator = ProvablyFairRandom("a" * 64, "client")
    reveal = generator.rotate_server_seed()
    tampered = type(reveal)(
        server_seed="b" * 64,
        client_seed=reveal.client_seed,
        commitment=reveal.commitment,
        rounds=reveal.rounds,
    )
    assert not tampered.verify()


def test_values_stay_in_range_and_cover_the_unit_interval():
    generator = ProvablyFairRandom("seed", "client")
    values = [generator.random() for _ in range(5_000)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert 0.45 < sum(values) / len(values) < 0.55


def test_supports_the_whole_random_api():
    generator = ProvablyFairRandom("seed", "client")
    deck = list(range(52))
    generator.shuffle(deck)
    assert sorted(deck) == list(range(52))
    assert generator.choice(deck) in deck
    assert len(generator.sample(deck, 5)) == 5
    assert 0 <= generator.randrange(37) < 37


def test_getrandbits_is_bounded():
    generator = ProvablyFairRandom("seed", "client")
    for bits in (1, 7, 8, 32, 53):
        assert 0 <= generator.getrandbits(bits) < (1 << bits)
    assert generator.getrandbits(0) == 0
    with pytest.raises(ValueError):
        generator.getrandbits(-1)


def test_changing_the_client_seed_resets_the_round_counter():
    generator = ProvablyFairRandom("a" * 64, "old", 9)
    generator.set_client_seed("new")
    assert generator.client_seed == "new"
    assert generator.nonce == 0


def test_next_round_advances_the_nonce():
    generator = ProvablyFairRandom("a" * 64, "client")
    assert generator.next_round() == 1
    assert generator.next_round() == 2
