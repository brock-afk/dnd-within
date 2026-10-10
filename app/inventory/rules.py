"""Coin math from the 2024 Player's Handbook: 1 platinum = 10 gold, and 1 gold = 2 electrum =
10 silver = 100 copper. Columns use the short names (pp, gp, ep, sp, cp)."""

# Each coin's worth in copper pieces, highest first.
COIN_VALUES = {"pp": 1000, "gp": 100, "ep": 50, "sp": 10, "cp": 1}


def gain(coins: dict[str, int], coin: str, amount: int) -> dict[str, int]:
    return {**coins, coin: coins[coin] + amount}


def spend(coins: dict[str, int], coin: str, amount: int) -> dict[str, int] | None:
    """Pay `amount` of `coin`. If there aren't enough of that coin, larger coins are broken into
    it, the smallest first (paying 5 silver with none breaks 1 gold into 10 silver, leaving 5).
    Smaller coins are never combined upward: that's a trip to the money changer. Returns the
    new coins, or None if even breaking every larger coin isn't enough."""
    coins = dict(coins)
    larger = [c for c, value in reversed(COIN_VALUES.items()) if value > COIN_VALUES[coin]]
    for big in larger:  # smallest larger coin first
        while coins[coin] < amount and coins[big] > 0:
            coins[big] -= 1
            coins[coin] += COIN_VALUES[big] // COIN_VALUES[coin]
    if coins[coin] < amount:
        return None
    coins[coin] -= amount
    return coins


# Every tool in the 2024 Player's Handbook, for "choose a tool proficiency": artisan's tools,
# then the other tools, with each gaming set and musical instrument on its own.
TOOLS = [
    "Alchemist's Supplies", "Brewer's Supplies", "Calligrapher's Supplies", "Carpenter's Tools",
    "Cartographer's Tools", "Cobbler's Tools", "Cook's Utensils", "Glassblower's Tools",
    "Jeweler's Tools", "Leatherworker's Tools", "Mason's Tools", "Painter's Supplies",
    "Potter's Tools", "Smith's Tools", "Tinker's Tools", "Weaver's Tools", "Woodcarver's Tools",
    "Disguise Kit", "Forgery Kit", "Herbalism Kit", "Navigator's Tools", "Poisoner's Kit",
    "Thieves' Tools",
    "Dice Set", "Dragonchess Set", "Playing Cards", "Three-Dragon Ante Set",
    "Bagpipes", "Drum", "Dulcimer", "Flute", "Horn", "Lute", "Lyre", "Pan Flute", "Shawm", "Viol",
]
