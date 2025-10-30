import asyncio
from aiohttp import ClientSession, ClientTimeout

class Communicator:

    def __init__(self, default_timeout: float = 0.5):

        self.session = ClientSession()
        self.default_timeout = default_timeout

    async def send_rpc(self, url: str, payload: dict, timeout: float = None):

        request_timeout = timeout if timeout is not None else self.default_timeout
        try:
            async with self.session.post(url, json=payload, timeout=request_timeout) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception:

            return None

    async def close(self):
        await self.session.close()