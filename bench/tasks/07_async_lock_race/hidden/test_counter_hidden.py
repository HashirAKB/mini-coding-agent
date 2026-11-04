import asyncio

from counters import Counter


def test_many_increments():
    async def main():
        counter = Counter()
        await asyncio.gather(*(counter.increment() for _ in range(200)))
        return counter.value

    assert asyncio.run(main()) == 200


def test_counters_are_independent():
    async def main():
        a, b = Counter(), Counter()
        await asyncio.gather(*(c.increment() for c in [a, b, a]))
        return a.value, b.value

    assert asyncio.run(main()) == (2, 1)
