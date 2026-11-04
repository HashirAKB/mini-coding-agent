def flatten(items):
    result = []
    for item in items:
        if hasattr(item, "__iter__"):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
