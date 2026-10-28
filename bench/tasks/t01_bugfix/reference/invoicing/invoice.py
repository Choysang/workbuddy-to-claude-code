"""Simple invoice model used by the billing service."""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def to_cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def check_discount(percent):
    percent = to_decimal(percent)
    if not Decimal(0) <= percent <= Decimal(100):
        raise ValueError(f"discount must be within 0..100, got {percent}")
    return percent


@dataclass
class LineItem:
    description: str
    unit_price: Decimal
    quantity: int = 1

    def __post_init__(self):
        self.unit_price = to_decimal(self.unit_price)

    def total(self):
        return self.unit_price * self.quantity


@dataclass
class Invoice:
    items: list = field(default_factory=list)
    discount_percent: Decimal = Decimal(0)

    def __post_init__(self):
        self.discount_percent = check_discount(self.discount_percent)

    def add(self, description, unit_price, quantity=1):
        self.items.append(LineItem(description, unit_price, quantity))

    def subtotal(self):
        return to_cents(sum((item.total() for item in self.items), Decimal(0)))

    def total(self):
        percent = check_discount(self.discount_percent)
        raw = sum((item.total() for item in self.items), Decimal(0))
        return to_cents(raw - raw * percent / 100)

    def render(self):
        lines = [f"{i.description:<20}{i.quantity:>4} x {i.unit_price:>8}" for i in self.items]
        lines.append(f"{'TOTAL':<20}{self.total():>17}")
        return "\n".join(lines)
