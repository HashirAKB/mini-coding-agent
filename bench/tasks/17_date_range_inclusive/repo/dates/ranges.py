from datetime import timedelta


def days_between(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days)]
