def purge_expired(entries, now):
    """`entries` maps key -> expiry timestamp. Remove expired keys in place."""
    removed = 0
    for key, expires_at in entries.items():
        if expires_at <= now:
            del entries[key]
            removed += 1
    return removed
