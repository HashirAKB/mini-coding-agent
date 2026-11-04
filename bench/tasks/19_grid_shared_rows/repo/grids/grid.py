def make_grid(rows, cols, fill=0):
    return [[fill] * cols] * rows


def set_cell(grid, row, col, value):
    grid[row][col] = value
