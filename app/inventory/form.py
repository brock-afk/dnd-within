from pydantic import BaseModel, ConfigDict

from app.core.forms import parse_amount
from app.inventory.rules import COINS, MAX_COINS


class CoinChangeForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount: str = ""
    coin: str = "gp"
    action: str = ""

    def count(self) -> int | None:
        return parse_amount(self.amount, 1, MAX_COINS)


class CoinForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pp: str = ""
    gp: str = ""
    ep: str = ""
    sp: str = ""
    cp: str = ""

    def values(self) -> dict[str, int | None]:
        return {
            column: parse_amount(getattr(self, column) or "0", 0, MAX_COINS) for column, _ in COINS
        }
