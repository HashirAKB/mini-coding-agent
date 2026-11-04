import asyncio
import time

from fetcher import fetch_all


async def slow_echo(url):
    await asyncio.sleep(0.2 if url == "first" else 0.0)
    return url


def test_order_is_preserved():
    assert asyncio.run(fetch_all(["first", "second"], slow_echo)) == ["first", "second"]


def test_runs_concurrently():
    async def nap(url):
        await asyncio.sleep(0.2)
        return url

    start = time.perf_counter()
    asyncio.run(fetch_all(list("abcde"), nap))
    assert time.perf_counter() - start < 0.6


def test_no_urls():
    assert asyncio.run(fetch_all([], slow_echo)) == []
