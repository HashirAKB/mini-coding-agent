from cache import purge_expired


def test_everything_expired():
    entries = {"a": 1, "b": 2}
    assert purge_expired(entries, now=10) == 2
    assert entries == {}


def test_nothing_expired():
    entries = {"a": 5}
    assert purge_expired(entries, now=1) == 0
    assert entries == {"a": 5}
