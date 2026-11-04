def median(values):
    """Median of a non-empty list of numbers."""
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
