"""One test per planted bug; the score is the number of these that pass."""

import datetime as dt
from decimal import Decimal

import pytest

from shopkit import cache, csvio, dates, inventory, orders, tax, util
from shopkit import money


def test_bug01_round_money_half_away_from_zero():
    assert money.round_money("2.675") == Decimal("2.68")
    assert money.round_money("2.665") == Decimal("2.67")
    assert money.round_money("-1.005") == Decimal("-1.01")


def test_bug02_add_months_clamps_to_month_end():
    assert dates.add_months(dt.date(2026, 3, 31), 1) == dt.date(2026, 4, 30)
    assert dates.add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)
    assert dates.add_months(dt.date(2026, 1, 30), 2) == dt.date(2026, 3, 30)
    assert dates.add_months(dt.date(2026, 5, 31), -1) == dt.date(2026, 4, 30)


def test_bug03_business_days_half_open():
    monday, next_monday = dt.date(2026, 10, 5), dt.date(2026, 10, 12)
    assert dates.business_days_between(monday, next_monday) == 5
    assert dates.business_days_between(monday, dt.date(2026, 10, 6)) == 1
    assert dates.business_days_between(monday, next_monday, holidays=[dt.date(2026, 10, 7)]) == 4


def test_bug04_progressive_tax_marginal_slices():
    assert tax.progressive_tax("25000") == Decimal("1500.00")
    assert tax.progressive_tax("60000") == Decimal("7000.00")
    assert tax.progressive_tax("5000") == Decimal("0.00")
    assert tax.progressive_tax("150000") == Decimal("30000.00")


def test_bug05_average_cost_weighted_by_units():
    stock = inventory.Stock()
    stock.receive(1, "10.00")
    stock.receive(3, "2.00")
    assert stock.average_cost() == Decimal("4.00")


def test_bug06_free_shipping_at_threshold():
    assert orders.shipping([orders.Line("A", 1, Decimal("50.00"))]) == Decimal("0")
    assert orders.shipping([orders.Line("A", 1, Decimal("49.99"))]) == Decimal("4.99")


def test_bug07_discount_excludes_shipping():
    lines = [orders.Line("A", 2, Decimal("10.00"))]
    # 20.00 * 0.9 + 4.99 shipping
    assert orders.order_total(lines, discount_pct=10) == Decimal("22.99")
    # Free shipping is decided before the discount: 60 * 0.5 = 30, still no fee.
    assert orders.order_total([orders.Line("B", 1, Decimal("60.00"))], discount_pct=50) == Decimal("30.00")


def test_bug08_csv_doubled_quote():
    assert csvio.parse_line('"say ""hi""",x') == ['say "hi"', "x"]
    assert csvio.parse_line('""""') == ['"']


def test_bug09_lru_get_refreshes_recency():
    lru = cache.LRUCache(2)
    lru.put("a", 1)
    lru.put("b", 2)
    assert lru.get("a") == 1
    lru.put("c", 3)
    assert lru.get("a") == 1
    assert lru.get("b") is None


def test_bug10_page_count_exact_and_empty():
    assert util.page_count(10, 5) == 2
    assert util.page_count(0, 5) == 0
    assert util.page_count(1, 5) == 1


def test_bug11_slugify_transliterates_accents():
    assert util.slugify("Café Crème") == "cafe-creme"
    assert util.slugify("Ångström über") == "angstrom-uber"


def test_bug12_parse_bool_case_insensitive():
    assert util.parse_bool("TRUE") is True
    assert util.parse_bool(" No ") is False
    assert util.parse_bool("Off") is False


def test_bug13_retry_total_attempts():
    calls = []

    def always_fails():
        calls.append(1)
        raise OSError("down")

    with pytest.raises(OSError):
        util.retry(always_fails, attempts=3)
    assert len(calls) == 3
