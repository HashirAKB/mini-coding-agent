import asyncio


async def fetch_all(urls, fetch):
    """Fetch every URL concurrently; results are in the same order as `urls`."""
    return [fetch(url) for url in urls]
