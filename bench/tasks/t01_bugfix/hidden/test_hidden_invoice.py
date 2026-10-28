from decimal import Decimal

import pytest

from invoicing import Invoice, LineItem


def test_subtotal_is_exact_decimal():
    inv = Invoice()
    for _ in range(3):
        inv.add("x", 0.10)
    assert inv.subtotal() == Decimal("0.30")


def test_ten_percent_discount_rounds_half_up():
    inv = Invoice(discount_percent=10)
    inv.add("x", 19.99)
    assert inv.total() == Decimal("17.99")


def test_half_cent_rounds_up():
    inv = Invoice()
    inv.add("x", Decimal("0.125"))
    assert inv.total() == Decimal("0.13")


def test_string_prices_are_accepted():
    inv = Invoice()
    inv.add("x", "1.10", 3)
    assert inv.total() == Decimal("3.30")


@pytest.mark.parametrize("pct", [-1, 100.01, 150])
def test_invalid_discount_raises(pct):
    with pytest.raises(ValueError):
        inv = Invoice(discount_percent=pct)
        inv.add("x", 10)
        inv.total()


def test_full_discount_is_zero():
    inv = Invoice(discount_percent=100)
    inv.add("x", 10)
    assert inv.total() == Decimal("0.00")


def test_line_item_total():
    assert LineItem("x", 0.1, 3).total() == Decimal("0.30")


def test_render_still_works():
    inv = Invoice()
    inv.add("widget", 2.5, 4)
    text = inv.render()
    assert "widget" in text and "10.00" in text
