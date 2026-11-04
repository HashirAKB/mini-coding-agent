from shop import add_item


def test_orders_are_independent():
    assert add_item("apple") == ["apple"]
    assert add_item("pear") == ["pear"]
