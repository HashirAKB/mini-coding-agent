from funcs import make_multipliers


def test_six():
    assert [m(1) for m in make_multipliers(6)] == [0, 1, 2, 3, 4, 5]


def test_count():
    assert len(make_multipliers(3)) == 3
