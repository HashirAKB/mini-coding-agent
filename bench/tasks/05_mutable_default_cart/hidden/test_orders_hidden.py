from shop import add_item


def test_explicit_list_is_extended():
    basket = ["milk"]
    assert add_item("bread", basket) is basket
    assert basket == ["milk", "bread"]


def test_many_fresh_orders():
    assert [len(add_item(i)) for i in range(3)] == [1, 1, 1]
