"""Money arithmetic on Decimal values in a single currency."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(value) -> Decimal:
    """Convert int, str or Decimal to Decimal. Floats are rejected with TypeError
    because they cannot represent cents exactly."""
    if isinstance(value, float):
        raise TypeError("use str or Decimal for money, not float")
    return Decimal(str(value))


def round_money(amount) -> Decimal:
    """Round to whole cents, halves away from zero (commercial rounding):
    2.675 -> 2.68, 2.665 -> 2.67, -1.005 -> -1.01."""
    return to_money(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def allocate(total, weights) -> list:
    """Split `total` into len(weights) cent amounts proportional to `weights`.
    The parts always sum exactly to round_money(total); leftover cents go to the
    parts with the largest weights first."""
    total = round_money(total)
    weight_sum = sum(weights)
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive number")
    cents = int(total * 100)
    shares = [cents * w // weight_sum for w in weights]
    leftover = cents - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: weights[i], reverse=True)
    for i in order[:leftover]:
        shares[i] += 1
    return [Decimal(s) / 100 for s in shares]
