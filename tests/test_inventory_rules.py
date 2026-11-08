from app.inventory import rules
from app.inventory.rules import Coin

EMPTY = {"pp": 0, "gp": 0, "ep": 0, "sp": 0, "cp": 0}


def test_gain():
    assert rules.gain(EMPTY, Coin.GOLD, 3)["gp"] == 3


def test_spend_from_same_coin():
    assert rules.spend({**EMPTY, "sp": 7}, Coin.SILVER, 5) == {**EMPTY, "sp": 2}


def test_spend_breaks_the_smallest_larger_coin_first():
    coins = {**EMPTY, "pp": 1, "gp": 1}
    assert rules.spend(coins, Coin.SILVER, 5) == {**EMPTY, "pp": 1, "sp": 5}


def test_spend_never_combines_smaller_coins():
    assert rules.spend({**EMPTY, "cp": 500}, Coin.GOLD, 1) is None


def test_spend_does_not_change_input():
    coins = {**EMPTY, "gp": 1}
    rules.spend(coins, Coin.COPPER, 1)
    assert coins == {**EMPTY, "gp": 1}
