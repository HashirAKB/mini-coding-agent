from cache import purge_expired


def test_removes_expired_entries():
    entries = {"a": 1, "b": 5, "c": 2}
    assert purge_expired(entries, now=2) == 2
    assert entries == {"b": 5}
