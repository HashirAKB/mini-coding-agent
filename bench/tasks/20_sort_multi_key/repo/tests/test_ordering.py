from hr import sort_employees


def test_department_then_salary():
    staff = [
        {"name": "a", "dept": "ops", "salary": 50},
        {"name": "b", "dept": "eng", "salary": 70},
        {"name": "c", "dept": "eng", "salary": 90},
    ]
    assert [e["name"] for e in sort_employees(staff)] == ["c", "b", "a"]
