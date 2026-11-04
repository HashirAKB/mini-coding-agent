import re

EMAIL = re.compile(r"^[a-z]+@[a-z]+\.[a-z]+$")


def is_valid_email(address):
    return EMAIL.match(address) is not None
