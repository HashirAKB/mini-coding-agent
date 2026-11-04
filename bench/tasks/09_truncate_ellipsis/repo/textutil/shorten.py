def truncate(text, max_len):
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
