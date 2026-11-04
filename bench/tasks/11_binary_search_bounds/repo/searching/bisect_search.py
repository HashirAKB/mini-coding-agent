def find(sorted_items, target):
    lo, hi = 0, len(sorted_items) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_items[mid] == target:
            return mid
        if sorted_items[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
