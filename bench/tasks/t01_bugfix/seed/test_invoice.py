from invoicing import Invoice


def test_simple_total():
    inv = Invoice()
    inv.add("widget", 2.5, 4)
    assert inv.total() == 10.0
