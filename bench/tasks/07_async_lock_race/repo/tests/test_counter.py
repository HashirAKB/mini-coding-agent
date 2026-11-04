import asyncio

from counters import Counter


def test_concurrent_increments():
    async def main():
        counter = Counter()
        await asyncio.gather(*(counter.increment() for _ in range(50)))
        return counter.value

    assert asyncio.run(main()) == 50
