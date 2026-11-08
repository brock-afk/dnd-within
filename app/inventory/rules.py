MAX_ATTUNED = 3
COINS = [("pp", "Platinum"), ("gp", "Gold"), ("ep", "Electrum"), ("sp", "Silver"), ("cp", "Copper")]
MAX_COINS = 1_000_000

COIN_VALUES = {"pp": 1000, "gp": 100, "ep": 50, "sp": 10, "cp": 1}


def gain(coins: dict[str, int], coin: str, amount: int) -> dict[str, int]:
    return {**coins, coin: coins[coin] + amount}


def spend(coins: dict[str, int], coin: str, amount: int) -> dict[str, int] | None:
    coins = dict(coins)
    larger = [c for c, value in reversed(COIN_VALUES.items()) if value > COIN_VALUES[coin]]
    for big in larger:
        while coins[coin] < amount and coins[big] > 0:
            coins[big] -= 1
            coins[coin] += COIN_VALUES[big] // COIN_VALUES[coin]
    if coins[coin] < amount:
        return None
    coins[coin] -= amount
    return coins


TOOLS = [
    "Alchemist's Supplies",
    "Brewer's Supplies",
    "Calligrapher's Supplies",
    "Carpenter's Tools",
    "Cartographer's Tools",
    "Cobbler's Tools",
    "Cook's Utensils",
    "Glassblower's Tools",
    "Jeweler's Tools",
    "Leatherworker's Tools",
    "Mason's Tools",
    "Painter's Supplies",
    "Potter's Tools",
    "Smith's Tools",
    "Tinker's Tools",
    "Weaver's Tools",
    "Woodcarver's Tools",
    "Disguise Kit",
    "Forgery Kit",
    "Herbalism Kit",
    "Navigator's Tools",
    "Poisoner's Kit",
    "Thieves' Tools",
    "Dice Set",
    "Dragonchess Set",
    "Playing Cards",
    "Three-Dragon Ante Set",
    "Bagpipes",
    "Drum",
    "Dulcimer",
    "Flute",
    "Horn",
    "Lute",
    "Lyre",
    "Pan Flute",
    "Shawm",
    "Viol",
]
