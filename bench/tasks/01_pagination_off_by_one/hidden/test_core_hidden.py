from pager import paginate


def test_last_partial_page():
    assert paginate(list(range(10)), 4, 3) == [9]


def test_page_past_the_end_is_empty():
    assert paginate(list(range(10)), 5, 3) == []


def test_single_item_pages():
    assert paginate(["a", "b"], 1, 1) == ["a"]
