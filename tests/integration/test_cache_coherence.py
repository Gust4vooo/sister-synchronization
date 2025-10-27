import asyncio
import aiohttp
import os
import sys
import redis.asyncio as redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.nodes.cache_node import CacheNode

NODE_CONFIGS = {
    "cache1": {"host": "127.0.0.1", "port": 10001},
    "cache2": {"host": "127.0.0.1", "port": 10002},
    "cache3": {"host": "127.0.0.1", "port": 10003},
}

async def main():
    # Setup Redis
    redis_client = redis.Redis(decode_responses=True)
    await redis_client.flushdb()
    await redis_client.set("A", "initial_value")
    print("--- Redis disiapkan dengan A = 'initial_value' ---")

    # Jalankan semua CacheNode
    node_tasks = []
    for node_id, config in NODE_CONFIGS.items():
        peers = {p_id: f"{p_cfg['host']}:{p_cfg['port']}" for p_id, p_cfg in NODE_CONFIGS.items() if p_id != node_id}
        node = CacheNode(node_id=node_id, host=config['host'], port=config['port'], peers=peers)
        node_tasks.append(asyncio.create_task(node.run()))
    await asyncio.sleep(2)

    try:
        async with aiohttp.ClientSession() as session:
            print("\n--- Skenario 1: Node 2 & 3 mengisi cache mereka dengan 'A' ---")
            await session.get("http://127.0.0.1:10002/read/A") # Miss 1 on node 2
            await session.get("http://127.0.0.1:10003/read/A") # Miss 1 on node 3
            
            print("\n--- Skenario 2: Node 1 menulis nilai baru ke 'A' ---")
            await session.post("http://127.0.0.1:10001/write", json={"key": "A", "value": "new_value"}) # Write 1 on node 1
            await asyncio.sleep(1) 
            
            print("\n--- Verifikasi: Node 2 membaca 'A' lagi ---")
            await session.get("http://127.0.0.1:10002/read/A") 
            
            await session.get("http://127.0.0.1:10003/read/A") 

            print("\n--- Metrik Kinerja Final ---")
            for node_id, config in NODE_CONFIGS.items():
                resp = await session.get(f"http://{config['host']}:{config['port']}/metrics")
                metrics = await resp.json()
                print(f"Metrics for {node_id}: {metrics}")

    finally:
        for task in node_tasks:
            task.cancel()
        await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())