"""Order totals: discounts, shipping and tax."""

from dataclasses import dataclass
from decimal import Decimal

from .money import round_money, to_money
from .tax import add_vat

FREE_SHIPPING_FROM = Decimal("50")
SHIPPING_FEE = Decimal("4.99")


@dataclass(frozen=True)
class Line:
    sku: str
    qty: int
    unit_price: Decimal


def subtotal(lines) -> Decimal:
    """Sum of qty * unit_price over all lines, rounded to cents."""
    return round_money(sum((line.qty * to_money(line.unit_price) for line in lines), Decimal("0")))


def shipping(lines) -> Decimal:
    """Flat SHIPPING_FEE, free when the item subtotal (before any discount) is at
    least FREE_SHIPPING_FROM. An empty order ships for free."""
    if not lines:
        return Decimal("0")
    return Decimal("0") if subtotal(lines) > FREE_SHIPPING_FROM else SHIPPING_FEE


def order_total(lines, discount_pct=0, vat_rate="0") -> Decimal:
    """Total to charge. The percentage discount applies to the item subtotal only,
    never to shipping. VAT is then added to (discounted items + shipping)."""
    discount = to_money(discount_pct) / 100
    if not 0 <= discount <= 1:
        raise ValueError("discount_pct must be between 0 and 100")
    net = (subtotal(lines) + shipping(lines)) * (1 - discount)
    return add_vat(round_money(net), vat_rate)
