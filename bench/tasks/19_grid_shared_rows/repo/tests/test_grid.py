from grids import make_grid, set_cell


def test_rows_are_independent():
    grid = make_grid(2, 2)
    set_cell(grid, 0, 0, 1)
    assert grid == [[1, 0], [0, 0]]
