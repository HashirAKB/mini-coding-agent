from hr import sort_employees


def test_ties_keep_original_order():
    staff = [
        {"name": "x", "dept": "eng", "salary": 10},
        {"name": "y", "dept": "eng", "salary": 10},
    ]
    assert [e["name"] for e in sort_employees(staff)] == ["x", "y"]


def test_three_departments():
    staff = [{"name": d, "dept": d, "salary": 1} for d in ["c", "a", "b"]]
    assert [e["name"] for e in sort_employees(staff)] == ["a", "b", "c"]
