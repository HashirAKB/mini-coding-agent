def moving_average(values, window):
    """Mean of each full window of `window` consecutive values."""
    return [sum(values[i : i + window]) / window for i in range(len(values) - window)]
