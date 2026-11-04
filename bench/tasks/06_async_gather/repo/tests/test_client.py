import asyncio

from fetcher import fetch_all


async def upper(url):
    return url.upper()


def test_results_not_coroutines():
    assert asyncio.run(fetch_all(["a", "b"], upper)) == ["A", "B"]
