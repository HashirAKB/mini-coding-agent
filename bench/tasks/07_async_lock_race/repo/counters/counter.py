import asyncio


class Counter:
    def __init__(self):
        self.value = 0

    async def increment(self):
        async with asyncio.Lock():
            current = self.value
            await asyncio.sleep(0)  # simulates an await between read and write
            self.value = current + 1
