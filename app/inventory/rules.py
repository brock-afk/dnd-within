from app.core.enums import LabeledEnum

MAX_ATTUNED = 3
MAX_COINS = 1_000_000


class Coin(LabeledEnum):
    PLATINUM = "pp"
    GOLD = "gp"
    ELECTRUM = "ep"
    SILVER = "sp"
    COPPER = "cp"

    @property
    def copper(self) -> int:
        return _COPPER[self]

    @property
    def noun(self) -> str:
        return self.label.lower()


_COPPER = {Coin.PLATINUM: 1000, Coin.GOLD: 100, Coin.ELECTRUM: 50, Coin.SILVER: 10, Coin.COPPER: 1}


class CoinChange(LabeledEnum):
    ADD = "gain"
    SPEND = "spend"


class ItemCategory(LabeledEnum):
    GEAR = "gear"
    CONSUMABLE = "consumable"
    PACK = "pack"
    SCROLL = "scroll"
    TOOL = "tool"
    MAGIC_ITEM = "magic"


class Rarity(LabeledEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    VERY_RARE = "very_rare"
    LEGENDARY = "legendary"
    ARTIFACT = "artifact"


def gain(coins: dict[str, int], coin: Coin, amount: int) -> dict[str, int]:
    return {**coins, coin: coins[coin] + amount}


def spend(coins: dict[str, int], coin: Coin, amount: int) -> dict[str, int] | None:
    coins = dict(coins)
    larger = [c for c in reversed(Coin) if c.copper > coin.copper]
    for big in larger:
        while coins[coin] < amount and coins[big] > 0:
            coins[big] -= 1
            coins[coin] += big.copper // coin.copper
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
