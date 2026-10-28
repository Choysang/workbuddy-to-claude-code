import datetime as dt
from decimal import Decimal

import pytest

from shopkit import cache, csvio, dates, inventory, money, orders, tax, util


def test_to_money_rejects_float():
    with pytest.raises(TypeError):
        money.to_money(1.5)


def test_round_money_plain_values():
    assert money.round_money("2.674") == Decimal("2.67")
    assert money.round_money("2.676") == Decimal("2.68")


def test_allocate_sums_to_total():
    parts = money.allocate("10.00", [1, 1, 1])
    assert sum(parts) == Decimal("10.00")
    assert parts[0] == Decimal("3.34")


def test_add_months_regular_day():
    assert dates.add_months(dt.date(2026, 8, 15), 1) == dt.date(2026, 9, 15)
    assert dates.add_months(dt.date(2026, 11, 10), 3) == dt.date(2027, 2, 10)


def test_add_months_end_of_january():
    assert dates.add_months(dt.date(2023, 1, 31), 1) == dt.date(2023, 2, 28)


def test_business_days_empty_range():
    assert dates.business_days_between(dt.date(2026, 10, 5), dt.date(2026, 10, 5)) == 0


def test_add_business_days_skips_weekend():
    friday = dt.date(2026, 10, 2)
    assert dates.add_business_days(friday, 1) == dt.date(2026, 10, 5)


def test_progressive_tax_top_bracket():
    # 0 + 3000 + 12000 + 15000
    assert tax.progressive_tax("150000") == Decimal("30000.00")


def test_vat_round_trip():
    assert tax.add_vat("10.00", "0.2") == Decimal("12.00")
    assert tax.remove_vat("12.00", "0.2") == Decimal("10.00")


def test_stock_fifo_cost():
    stock = inventory.Stock()
    stock.receive(5, "2.00")
    stock.receive(5, "3.00")
    assert stock.consume(7) == Decimal("16.00")
    assert stock.on_hand == 3


def test_stock_insufficient():
    stock = inventory.Stock()
    stock.receive(1, "1")
    with pytest.raises(ValueError):
        stock.consume(2)


def test_average_cost_single_lot():
    stock = inventory.Stock()
    stock.receive(1, "2.50")
    assert stock.average_cost() == Decimal("2.50")


def test_order_total_without_discount():
    lines = [orders.Line("A", 2, Decimal("10.00"))]
    assert orders.order_total(lines) == Decimal("24.99")


def test_free_shipping_large_order():
    lines = [orders.Line("A", 1, Decimal("80.00"))]
    assert orders.shipping(lines) == Decimal("0")


def test_parse_line_quoted_separator():
    assert csvio.parse_line('a,"b,c",d') == ["a", "b,c", "d"]


def test_price_feed():
    feed = "sku,price\nA1,9.99\n\nB2,0.50\n"
    assert csvio.parse_price_feed(feed) == {"A1": Decimal("9.99"), "B2": Decimal("0.50")}


def test_lru_evicts_oldest():
    lru = cache.LRUCache(2)
    lru.put("a", 1)
    lru.put("b", 2)
    lru.put("c", 3)
    assert lru.get("a") is None
    assert len(lru) == 2


def test_page_count_partial_page():
    assert util.page_count(11, 5) == 3


def test_slugify_ascii():
    assert util.slugify("  Hello,  World! ") == "hello-world"


def test_parse_bool_words():
    assert util.parse_bool("yes") is True
    assert util.parse_bool(" off ") is False
    with pytest.raises(ValueError):
        util.parse_bool("maybe")


def test_retry_returns_first_success():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise OSError("boom")
        return "ok"

    assert util.retry(flaky) == "ok"
