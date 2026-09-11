import pytest

from pysino.core.cards import Card, Deck, Shoe, full_deck, parse_hand


def test_full_deck_has_52_unique_cards():
    deck = full_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52


@pytest.mark.parametrize(
    "text,rank,suit",
    [("As", 14, "s"), ("10h", 10, "h"), ("Td", 10, "d"), ("2c", 2, "c"), ("kS", 13, "s")],
)
def test_parse_accepts_the_usual_shorthand(text, rank, suit):
    card = Card.parse(text)
    assert (card.rank, card.suit) == (rank, suit)


@pytest.mark.parametrize("text", ["", "X", "1s", "Ax", "15h"])
def test_parse_rejects_nonsense(text):
    with pytest.raises(ValueError):
        Card.parse(text)


def test_blackjack_values():
    assert Card.parse("As").blackjack_value == 11
    assert Card.parse("Ks").blackjack_value == 10
    assert Card.parse("10s").blackjack_value == 10
    assert Card.parse("7s").blackjack_value == 7


def test_deck_deals_without_repeating(rng):
    deck = Deck(rng)
    dealt = deck.deal(52)
    assert len(set(dealt)) == 52
    assert len(deck) == 0
    with pytest.raises(IndexError):
        deck.draw()


def test_shoe_holds_the_right_number_of_cards(rng):
    shoe = Shoe(rng, decks=6)
    assert shoe.total_cards == 312
    assert shoe.cards_remaining == 312


def test_shoe_flags_a_reshuffle_at_the_cut_card(rng):
    shoe = Shoe(rng, decks=1, penetration=0.5)
    assert not shoe.needs_shuffle
    shoe.deal(26)
    assert shoe.needs_shuffle
    shoe.shuffle()
    assert not shoe.needs_shuffle
    assert shoe.cards_remaining == 52


def test_shoe_never_runs_dry(rng):
    shoe = Shoe(rng, decks=1, penetration=1.0)
    drawn = [shoe.draw() for _ in range(120)]
    assert len(drawn) == 120
    assert shoe.shuffles > 1


def test_parse_hand_reads_a_whole_hand():
    assert [str(card) for card in parse_hand("As Kd 10h")] == ["As", "Kd", "10h"]


@pytest.mark.parametrize("rank,suit", [(1, "s"), (15, "h"), (5, "x")])
def test_invalid_cards_are_rejected(rank, suit):
    with pytest.raises(ValueError):
        Card(rank, suit)
