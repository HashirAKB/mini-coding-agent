from validators import is_valid_email


def test_plus_and_dot_are_allowed():
    assert is_valid_email("john.doe+news@example.com")


def test_missing_tld_is_rejected():
    assert not is_valid_email("a@b")
