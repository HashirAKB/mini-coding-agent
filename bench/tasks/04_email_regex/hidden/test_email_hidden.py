from validators import is_valid_email


def test_digits_uppercase_and_subdomains():
    assert is_valid_email("USER1@mail.example.co.uk")


def test_missing_at_sign():
    assert not is_valid_email("no-at-sign.com")


def test_empty_domain_label():
    assert not is_valid_email("x@.com")
