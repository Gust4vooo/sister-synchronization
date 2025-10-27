import asyncio
import aiohttp
import os
import sys
import redis.asyncio as redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.nodes.cache_node import CacheNode

async def main():
    redis_client = redis.Redis(decode_responses=True)
    await redis_client.flushdb()
    print("--- Database Redis dibersihkan ---")

    node = CacheNode(node_id="cache1", host="127.0.0.1", port=10001, peers={}, max_cache_size=3)
    node_task = asyncio.create_task(node.run())
    await asyncio.sleep(2)

    try:
        async with aiohttp.ClientSession() as session:
            print("\n--- Skenario 1: Mengisi Cache ---")
            await session.post("http://127.0.0.1:10001/write", json={"key": "A", "value": "1"})
            await session.post("http://127.0.0.1:10001/write", json={"key": "B", "value": "2"})
            await session.post("http://127.0.0.1:10001/write", json={"key": "C", "value": "3"})
            
            print("\n--- Skenario 2: Membaca 'A' ---")
            await session.get("http://127.0.0.1:10001/read/A") 
            
            print("\n--- Skenario 3: Menulis 'D', harusnya menghapus 'B' ---")
            await session.post("http://127.0.0.1:10001/write", json={"key": "D", "value": "4"})
            
            print("\n--- Verifikasi: Membaca 'B' ---")
            resp = await session.get("http://127.0.0.1:10001/read/B")
            data = await resp.json()
            if data.get("source") == "redis":
                print("\n✅ BERHASIL! 'B' adalah Cache Miss, kebijakan LRU bekerja.")
            else:
                print("\n❌ GAGAL! 'B' seharusnya sudah dihapus dari cache.")
            
    finally:
        node_task.cancel()
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())