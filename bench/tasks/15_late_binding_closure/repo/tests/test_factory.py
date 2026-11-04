from funcs import make_multipliers


def test_each_function_uses_its_own_factor():
    assert [m(2) for m in make_multipliers(4)] == [0, 2, 4, 6]
