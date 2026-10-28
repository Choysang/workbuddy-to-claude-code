"""Progressive tax and VAT helpers."""

from decimal import Decimal

from .money import round_money, to_money

# (lower bound, upper bound or None, rate) - marginal brackets.
DEFAULT_BRACKETS = (
    (Decimal("0"), Decimal("10000"), Decimal("0.00")),
    (Decimal("10000"), Decimal("40000"), Decimal("0.10")),
    (Decimal("40000"), Decimal("100000"), Decimal("0.20")),
    (Decimal("100000"), None, Decimal("0.30")),
)


def progressive_tax(income, brackets=DEFAULT_BRACKETS) -> Decimal:
    """Marginal tax: each bracket's rate applies only to the part of income that
    falls inside that bracket. Income <= 0 pays 0. Result rounded to cents."""
    income = to_money(income)
    tax = Decimal("0")
    for lower, upper, rate in brackets:
        top = income if upper is None else min(income, upper)
        tax += (top - lower) * rate
    return round_money(max(tax, Decimal("0")))


def add_vat(net, rate) -> Decimal:
    """Gross price for a net price and a VAT rate given as a fraction (0.2 = 20%)."""
    return round_money(to_money(net) * (1 + to_money(rate)))


def remove_vat(gross, rate) -> Decimal:
    """Net price contained in a gross price for a VAT rate given as a fraction."""
    return round_money(to_money(gross) / (1 + to_money(rate)))
