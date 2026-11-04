SYMBOLS = [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]


def to_roman(n):
    result = ""
    for value, symbol in SYMBOLS:
        while n >= value:
            result += symbol
            n -= value
    return result
