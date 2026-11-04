from grids import make_grid, set_cell


def test_shape():
    grid = make_grid(3, 4, fill=".")
    assert len(grid) == 3 and all(len(row) == 4 for row in grid)


def test_diagonal():
    grid = make_grid(3, 3)
    for i in range(3):
        set_cell(grid, i, i, 1)
    assert grid == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
